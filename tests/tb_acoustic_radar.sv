`timescale 1ns/1ps
module tb_acoustic_radar;
    logic clk = 0;
    always #5 clk = ~clk;
    logic resetn = 0;
    logic enable = 0;
    logic [5:0] sd = 0;
    wire sck, ws, frame_valid;
    wire [143:0] samples;
    logic [10:0] index = 0;
    wire [31:0] window_samples, value, sequence_id, frames, dropped;
    wire [191:0] levels;
    localparam [143:0] EXPECTED = {24'h007fff, 24'h800000, 24'h7fffff, 24'hf4b876, 24'h6ac2f1, 24'hbcdef0};
    int delays [6] = '{2, 1, 0, 4, 3, 2};
    int position = 0;
    int rises = 0;
    int pair = 0;
    time last_rise;

    i2s_six capture(clk, resetn, enable, sd, sck, ws, frame_valid, samples);
    correlator #(.WINDOW(64), .STARTUP_FRAMES(8)) engine(clk, resetn, enable, 1'b1,
        frame_valid, samples, index, value, sequence_id, frames, dropped, levels, window_samples);

    always @(negedge sck) if (enable) begin
        position = (position + 1) % 64;
        for (int mic = 0; mic < 6; mic++)
            sd[mic] = position >= 1 && position <= 24 ? EXPECTED[mic * 24 + 24 - position] : 1'b1;
    end

    always @(posedge sck) begin
        if (ws != (rises % 64 >= 32)) $fatal(1, "Incorrect WS at bit %0d", rises);
        if (rises != 0 && ($time - last_rise < 320 || $time - last_rise > 330))
            $fatal(1, "Invalid SCK period");
        last_rise = $time;
        rises++;
    end

    always @(negedge clk)
        if (frame_valid && samples != EXPECTED) $fatal(1, "I2S sample mismatch %036x", samples);

    initial begin
        repeat (5) @(negedge clk);
        resetn = 1;
        enable = 1;
        wait(sequence_id == 2);
        for (int first = 0; first < 6; first++) begin
            for (int second = first + 1; second < 6; second++, pair++) begin
                int best_lag = 0;
                int best = -2147483647;
                for (int bin = 0; bin < 65; bin++) begin
                    @(negedge clk);
                    index = 11'(pair * 65 + bin);
                    @(negedge clk);
                    if ($signed(value) > best) begin
                        best = $signed(value);
                        best_lag = bin - 32;
                    end
                end
                if (best_lag != delays[second] - delays[first] || best <= 0)
                    $fatal(1, "Pair %0d/%0d had lag %0d", first, second, best_lag);
            end
        end
        if (dropped != 0 || levels == 0) $fatal(1, "Unexpected board counters");
        $display("PASS: six I2S words, SCK/WS timing, all 15 correlation peaks, alternating snapshot banks");
        $finish;
    end
    initial begin
        #6000000;
        $fatal(1, "Simulation timed out");
    end
endmodule
