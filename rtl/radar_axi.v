`timescale 1ns/1ps
module radar_axi (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    input wire s_axi_aresetn,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 18, READ_WRITE_MODE READ_WRITE" *)
    input wire [17:0] s_axi_awaddr,
    input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [17:0] s_axi_araddr,
    input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    input wire mic1_sd, mic2_sd, mic3_sd, mic4_sd, mic5_sd, mic6_sd,
    output wire i2s_sck, i2s_ws
);
    reg [1:0] mode;
    reg aw_saved, w_saved;
    reg [17:0] write_address;
    reg [1:0] write_mode;
    reg write_low_byte;
    reg [17:0] read_address;
    reg [1:0] read_pending;
    wire [143:0] samples;
    wire frame_valid;
    wire [31:0] sequence_id, frame_count, dropped_frames, read_value, window_samples;
    wire [191:0] levels;

    (* ASYNC_REG = "TRUE" *) reg [5:0] sd_meta, sd_sync;
    always @(posedge s_axi_aclk) begin
        sd_meta <= {mic6_sd, mic5_sd, mic4_sd, mic3_sd, mic2_sd, mic1_sd};
        sd_sync <= sd_meta;
    end

    wire sck, ws;
    // Hold external clocks low during the internal self-test.
    assign i2s_sck = sck && !mode[1];
    assign i2s_ws = ws && !mode[1];
    i2s_six i2s (
        .clk(s_axi_aclk), .resetn(s_axi_aresetn), .enable(mode[0]), .sd(sd_sync),
        .sck(sck), .ws(ws), .frame_valid(frame_valid), .samples(samples)
    );
    correlator processor (
        .clk(s_axi_aclk), .resetn(s_axi_aresetn), .enable(mode[0]), .test_source(mode[1]),
        .frame_valid(frame_valid), .samples(samples), .read_index({1'b0, read_address[11:2]}),
        .read_value(read_value), .sequence_id(sequence_id), .frame_count(frame_count),
        .dropped_frames(dropped_frames), .levels(levels), .window_samples(window_samples)
    );

    // 170 ms of simultaneous, signed 24-bit I2S words for lossless take capture.
    // Six independent read windows start at byte address 0x10000, stride 0x8000.
    wire [23:0] pcm_rd [0:5];
    genvar mic;
    generate for (mic = 0; mic < 6; mic = mic + 1) begin : pcm_channel
        (* ram_style = "block" *) reg [23:0] memory [0:8191];
        reg [23:0] value;
        always @(posedge s_axi_aclk) begin
            if (frame_valid && mode == 1)
                memory[frame_count[12:0]] <= samples[mic*24 +: 24];
            value <= memory[read_address[14:2]];
        end
        assign pcm_rd[mic] = value;
    end endgenerate

    assign s_axi_awready = !aw_saved && !s_axi_bvalid;
    assign s_axi_wready = !w_saved && !s_axi_bvalid;
    assign s_axi_bresp = 2'b00;
    assign s_axi_arready = read_pending == 0 && !s_axi_rvalid;
    assign s_axi_rresp = 2'b00;

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            mode <= 0;
            aw_saved <= 0;
            w_saved <= 0;
            write_address <= 0;
            write_mode <= 0;
            write_low_byte <= 0;
            s_axi_bvalid <= 0;
            read_address <= 0;
            read_pending <= 0;
            s_axi_rdata <= 0;
            s_axi_rvalid <= 0;
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin
                aw_saved <= 1;
                write_address <= s_axi_awaddr;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                w_saved <= 1;
                write_mode <= s_axi_wdata[1:0];
                write_low_byte <= s_axi_wstrb[0];
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (aw_saved && w_saved) begin
                if (write_address == 18'h0008 && write_low_byte) mode <= write_mode;
                aw_saved <= 0;
                w_saved <= 0;
                s_axi_bvalid <= 1;
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0;
            if (s_axi_arvalid && s_axi_arready) begin
                read_address <= s_axi_araddr;
                read_pending <= 2;
            end else if (read_pending != 0) begin
                read_pending <= read_pending - 1'b1;
                if (read_pending == 1) begin
                    s_axi_rvalid <= 1;
                    case (read_address)
                        18'h0000: s_axi_rdata <= 32'h41524452; // ARDR
                        18'h0004: s_axi_rdata <= 32'h00010000;
                        18'h0008: s_axi_rdata <= {30'd0, mode};
                        18'h000c: s_axi_rdata <= sequence_id;
                        18'h0010: s_axi_rdata <= frame_count;
                        18'h0014: s_axi_rdata <= dropped_frames;
                        18'h0020: s_axi_rdata <= levels[31:0];
                        18'h0024: s_axi_rdata <= levels[63:32];
                        18'h0028: s_axi_rdata <= levels[95:64];
                        18'h002c: s_axi_rdata <= levels[127:96];
                        18'h0030: s_axi_rdata <= levels[159:128];
                        18'h0034: s_axi_rdata <= levels[191:160];
                        18'h003c: s_axi_rdata <= window_samples;
                        18'h0038: s_axi_rdata <= 32'h50434d36; // PCM6
                        default: s_axi_rdata <= read_address >= 18'h10000
                            ? {8'd0, pcm_rd[read_address[17:15] - 3'd2]} : (read_address >= 18'h1000 && read_address <= 18'h1f38)
                            ? read_value : 32'd0;
                    endcase
                end
            end
        end
    end
endmodule
