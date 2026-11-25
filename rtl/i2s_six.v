`timescale 1ns/1ps
module i2s_six (
    input  wire         clk,
    input  wire         resetn,
    input  wire         enable,
    input  wire [5:0]   sd,
    output reg          sck,
    output reg          ws,
    output reg          frame_valid,
    output reg  [143:0] samples
);
    // 6.144 MHz edge rate from the 100 MHz FCLK: 192 / 3125.
    // SCK half cycles alternate between 160 and 170 ns.
    reg [11:0] phase;
    wire [12:0] next_phase = {1'b0, phase} + 13'd192;
    wire clock_edge = next_phase >= 13'd3125;
    wire [12:0] wrapped_phase = next_phase - 13'd3125;
    reg [5:0] bit_position;
    reg [143:0] shifting;
    integer channel;

    always @(posedge clk) begin
        if (!resetn || !enable) begin
            phase <= 0;
            sck <= 0;
            ws <= 0;
            bit_position <= 0;
            frame_valid <= 0;
            shifting <= 0;
            samples <= 0;
        end else begin
            frame_valid <= 0;
            phase <= clock_edge ? wrapped_phase[11:0] : next_phase[11:0];
            if (clock_edge) begin
                sck <= !sck;
                if (sck) begin
                    bit_position <= bit_position + 6'd1;
                    if (bit_position == 6'd31) ws <= 1;
                    if (bit_position == 6'd63) ws <= 0;
                end else if (bit_position >= 6'd1 && bit_position <= 6'd24) begin
                    // Capture on rising SCK, starting one full bit after WS.
                    for (channel = 0; channel < 6; channel = channel + 1) begin
                        shifting[24*channel +: 24] <= {shifting[24*channel +: 23], sd[channel]};
                        if (bit_position == 6'd24)
                            samples[24*channel +: 24] <= {shifting[24*channel +: 23], sd[channel]};
                    end
                    if (bit_position == 6'd24) frame_valid <= 1;
                end
            end
        end
    end
endmodule
