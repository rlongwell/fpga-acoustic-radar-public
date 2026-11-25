`timescale 1ns/1ps
module correlator #(
    parameter WINDOW = 4096,
    parameter STARTUP_FRAMES = 4096
) (
    input  wire         clk,
    input  wire         resetn,
    input  wire         enable,
    input  wire         test_source,
    input  wire         frame_valid,
    input  wire [143:0] samples,
    input  wire [10:0]  read_index,
    output reg  [31:0]  read_value,
    output reg  [31:0]  sequence_id,
    output reg  [31:0]  frame_count,
    output reg  [31:0]  dropped_frames,
    output reg  [191:0] levels,
    output reg  [31:0] window_samples
);
    localparam IDLE = 2'd0, READ = 2'd1, ADD = 2'd2;
    localparam LAG = 32, LAST_BIN = 974;
    reg [1:0] state;
    reg published_bank;
    reg [31:0] accumulators [0:1023];
    reg [31:0] snapshots [0:2047];
    reg [31:0] energy [0:5];
    reg [23:0] previous [0:5];
    reg signed [9:0] history [0:5][0:LAG];
    reg signed [9:0] prbs_delay [0:3];
    reg [15:0] prbs;
    wire signed [9:0] prbs_sample = $signed(prbs[9:0]);
    reg sample_pending, power_pending;
    reg signed [9:0] staged_sample [0:5];
    reg [19:0] staged_power [0:5];
    reg [31:0] window_frame;
    reg [9:0] index;
    reg [2:0] mic_i, mic_j;
    reg [6:0] lag_index;
    wire [5:0] delay_amount = (lag_index >= 7'd32) ? lag_index[5:0] - 6'd32 : 6'd32 - lag_index[5:0];
    reg signed [9:0] operand_a, operand_b;
    reg signed [31:0] prior_sum;
    wire signed [19:0] product = operand_a * operand_b;
    wire final_frame = window_frame == WINDOW - 1;
    // Retire the multiply and accumulation on separate clocks. The following
    // bin reads a different RAM address while this one is being written.
    reg write_pending, write_snapshot, write_bank;
    reg [9:0] write_index;
    reg signed [19:0] write_product;
    reg signed [31:0] write_prior;
    wire signed [31:0] updated_sum = write_prior + {{12{write_product[19]}}, write_product};
    always @(posedge clk) begin
        write_pending <= resetn && enable && state == ADD;
        if (state == ADD) begin
            write_product <= product;
            write_prior <= prior_sum;
            write_index <= index;
            write_bank <= !published_bank;
            write_snapshot <= final_frame;
        end
    end
    integer mic, age;

    function signed [9:0] difference;
        input [23:0] now_sample;
        input [23:0] prior_sample;
        reg signed [24:0] delta, scaled;
        begin
            delta = $signed({now_sample[23], now_sample}) - $signed({prior_sample[23], prior_sample});
            scaled = delta >>> 5;
            if (scaled > 25'sd511) difference = 10'sd511;
            else if (scaled < -25'sd512) difference = -10'sd512;
            else difference = scaled[9:0];
        end
    endfunction

    wire signed [9:0] next_sample [0:5];
    genvar channel;
    generate for (channel = 0; channel < 6; channel = channel + 1) begin : channel_input
        // Built-in test arrival delays in samples for MIC1 through MIC6.
        localparam TEST_DELAY = (channel == 0) ? 2 : (channel == 1) ? 1 :
                                (channel == 2) ? 0 : (channel == 3) ? 4 :
                                (channel == 4) ? 3 : 2;
        wire signed [9:0] test_value;
        if (TEST_DELAY == 0) assign test_value = prbs_sample;
        else assign test_value = prbs_delay[TEST_DELAY - 1];
        assign next_sample[channel] = test_source ? test_value :
            difference(samples[24*channel +: 24], previous[channel]);
    end endgenerate

    // PS reads the completed bank. Check sequence again after a bulk read.
    // Keep physical RAM read addresses at ten bits even on invalid requests.
    always @(posedge clk)
        if (write_pending && write_snapshot)
            snapshots[{write_bank, write_index}] <= updated_sum;
    always @(posedge clk)
        read_value <= snapshots[{published_bank, read_index[9:0]}];

    always @(posedge clk) begin
        if (state == READ) prior_sum <= window_frame == 0 ? 32'sd0 : $signed(accumulators[index]);
        if (write_pending) accumulators[write_index] <= updated_sum;
    end

    always @(posedge clk) begin
        if (!resetn || !enable) begin
            state <= IDLE;
            sequence_id <= 0;
            window_samples <= 0;
            frame_count <= 0;
            dropped_frames <= 0;
            levels <= 0;
            published_bank <= 0;
            window_frame <= 0;
            index <= 0;
            mic_i <= 0;
            mic_j <= 1;
            lag_index <= 0;
            prbs <= 16'hace1;
            sample_pending <= 0;
            power_pending <= 0;
            operand_a <= 0;
            operand_b <= 0;
            // Delay histories warm up before use, while the microphones start.
            for (mic = 0; mic < 6; mic = mic + 1) begin
                energy[mic] <= 0;
                previous[mic] <= 0;
            end
        end else begin
            if (write_pending && write_snapshot && write_index == LAST_BIN) begin
                published_bank <= write_bank;
                sequence_id <= sequence_id + 1;
                window_samples <= frame_count;
            end
            sample_pending <= frame_valid && state == IDLE;
            power_pending <= sample_pending;
            if (frame_valid) begin
                frame_count <= frame_count + 1;
                if (state != IDLE) dropped_frames <= dropped_frames + 1;
                if (state == IDLE) begin
                    prbs <= {prbs[14:0], prbs[15] ^ prbs[13] ^ prbs[12] ^ prbs[10]};
                    prbs_delay[0] <= prbs_sample;
                    for (age = 1; age < 4; age = age + 1)
                        prbs_delay[age] <= prbs_delay[age-1];
                    for (mic = 0; mic < 6; mic = mic + 1) begin
                        previous[mic] <= samples[24*mic +: 24];
                        staged_sample[mic] <= next_sample[mic];
                    end
                end
            end
            if (sample_pending) begin
                for (mic = 0; mic < 6; mic = mic + 1) begin
                    history[mic][0] <= staged_sample[mic];
                    for (age = 1; age <= LAG; age = age + 1)
                        history[mic][age] <= history[mic][age-1];
                    staged_power[mic] <= staged_sample[mic] * staged_sample[mic];
                end
            end
            if (power_pending && frame_count > STARTUP_FRAMES + LAG) begin
                for (mic = 0; mic < 6; mic = mic + 1) begin
                    energy[mic] <= window_frame == 0 ? {12'd0, staged_power[mic]} :
                        energy[mic] + {12'd0, staged_power[mic]};
                end
                index <= 0;
                mic_i <= 0;
                mic_j <= 1;
                lag_index <= 0;
                state <= READ;
            end
            if (state == READ) begin
                // Positive lag means the wave reaches j after i.
                operand_a <= history[mic_i][lag_index >= 7'd32 ? delay_amount : 6'd0];
                operand_b <= history[mic_j][lag_index < 7'd32 ? delay_amount : 6'd0];
                state <= ADD;
            end else if (state == ADD) begin
                if (index == LAST_BIN) begin
                    if (final_frame) begin
                        for (mic = 0; mic < 6; mic = mic + 1) levels[32*mic +: 32] <= energy[mic];
                        window_frame <= 0;
                    end else begin
                        window_frame <= window_frame + 1;
                    end
                    state <= IDLE;
                end else begin
                    index <= index + 1'b1;
                    if (lag_index == 7'd64) begin
                        lag_index <= 0;
                        if (mic_j == 3'd5) begin
                            mic_i <= mic_i + 1'b1;
                            mic_j <= mic_i + 3'd2;
                        end else begin
                            mic_j <= mic_j + 1'b1;
                        end
                    end else begin
                        lag_index <= lag_index + 1'b1;
                    end
                    state <= READ;
                end
            end
        end
    end
endmodule
