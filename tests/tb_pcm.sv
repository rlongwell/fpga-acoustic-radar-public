`timescale 1ns/1ps
module tb_pcm;
    logic clk = 0, resetn = 0;
    always #5 clk = ~clk;
    logic [17:0] awaddr, araddr;
    logic awvalid, wvalid, arvalid, rready;
    logic [31:0] wdata;
    wire awready, wready, bvalid, arready, rvalid, sck, ws;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    logic [5:0] sd = 0;
    int word = 0, slot = 0;
    radar_axi dut(.s_axi_aclk(clk), .s_axi_aresetn(resetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hf), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(1'b1),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .mic1_sd(sd[0]), .mic2_sd(sd[1]), .mic3_sd(sd[2]), .mic4_sd(sd[3]),
        .mic5_sd(sd[4]), .mic6_sd(sd[5]), .i2s_sck(sck), .i2s_ws(ws));

    function automatic logic [23:0] sample(int channel, int index);
        return 24'(32'h892817 + channel * 32'h164137 + index * 701);
    endfunction
    always @(negedge sck) begin
        slot = (slot + 1) % 64;
        if (slot == 0) word++;
        for (int c=0; c<6; c++) begin
            logic [23:0] value;
            value = sample(c, word);
            sd[c] = slot >= 1 && slot <= 24 ? value[24-slot] : 0;
        end
    end
    task automatic read_check(input logic [17:0] address, input logic [31:0] expected);
        @(negedge clk);
        arvalid = 1; araddr = address; rready = 0;
        @(negedge clk);
        arvalid = 0;
        wait(rvalid);
        repeat(2) @(negedge clk);
        if (rdata !== expected) $fatal(1,"Address %h read %h, expected %h",address,rdata,expected);
        rready=1;
        @(negedge clk);
        rready=0;
    endtask
    initial begin
        repeat(5) @(negedge clk);
        resetn = 1;
        read_check(18'h38,32'h50434d36);
        @(negedge clk);
        awaddr=8; wdata=1; awvalid=1; wvalid=1;
        @(negedge clk); awvalid=0; wvalid=0;
        wait(dut.frame_count == 8194);
        for (int c=0; c<6; c++) begin
            read_check(18'(32'h10000+c*32768), {8'h00,sample(c,8192)});
            read_check(18'(32'h10004+c*32768), {8'h00,sample(c,8193)});
            read_check(18'(32'h17ffc+c*32768), {8'h00,sample(c,8191)});
        end
        wait(dut.sequence_id == 1);
        read_check(18'h3c, 4096+32+4096);
        $display("PASS: 6 PCM channels, sample identity, 8192-word wrap, window timestamp and AXI backpressure");
        $finish;
    end
    initial begin
        repeat(18000000) @(posedge clk);
        $fatal(1,"PCM simulation timed out");
    end
endmodule
