set root [file normalize [file join [file dirname [info script]] ..]]
if {![string match "2024.2*" [version -short]]} {error "Use Vivado 2024.2"}
set build [file join $root build fpga]
file mkdir $build
set_param general.maxThreads 4
if {[info exists ::env(ZYBO_BOARD_REPO)]} {
    set board_repo $::env(ZYBO_BOARD_REPO)
} else {
    set board_repo [file join $root constraints board_files]
}
if {![file isdirectory $board_repo]} {error "Set ZYBO_BOARD_REPO to the Digilent Vivado board-file directory"}
set_param board.repoPaths [list $board_repo]
create_project -force acoustic_radar $build -part xc7z020clg400-1
set_property board_part digilentinc.com:zybo-z7-20:part0:1.2 [current_project]
set_property target_language Verilog [current_project]
add_files [glob [file join $root rtl *.v]]
add_files -fileset constrs_1 [list \
    [file join $root constraints zybo_z7_20_je_inmp441_6mic.xdc] \
    [file join $root constraints radar_timing.xdc]]
update_compile_order -fileset sources_1

create_bd_design radar_system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} [get_bd_cells ps7]
set_property -dict {CONFIG.PCW_USE_M_AXI_GP0 1 CONFIG.PCW_EN_CLK0_PORT 1 CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ 100} [get_bd_cells ps7]
create_bd_cell -type module -reference radar_axi radar
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 control
set_property -dict {CONFIG.NUM_SI 1 CONFIG.NUM_MI 1} [get_bd_cells control]
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins control/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins control/M00_AXI] [get_bd_intf_pins radar/s_axi]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset
set_property CONFIG.C_EXT_RESET_HIGH 0 [get_bd_cells reset]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one
set_property CONFIG.CONST_VAL 1 [get_bd_cells one]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset/dcm_locked]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins reset/ext_reset_in]
foreach pin {ps7/M_AXI_GP0_ACLK reset/slowest_sync_clk control/ACLK control/S00_ACLK control/M00_ACLK radar/s_axi_aclk} {
    connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {control/ARESETN control/S00_ARESETN control/M00_ARESETN radar/s_axi_aresetn} {
    connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins $pin]
}
foreach pin {i2s_sck i2s_ws mic1_sd mic2_sd mic3_sd mic4_sd mic5_sd mic6_sd} {
    set direction [expr {[string match "mic*" $pin] ? "I" : "O"}]
    create_bd_port -dir $direction $pin
    connect_bd_net [get_bd_ports $pin] [get_bd_pins radar/$pin]
}
set segment [get_bd_addr_segs -of_objects [get_bd_intf_pins radar/s_axi]]
assign_bd_address -offset 0x43c00000 -range 256K \
    -target_address_space [get_bd_addr_spaces ps7/Data] $segment
validate_bd_design
save_bd_design
set design [get_files */radar_system.bd]
generate_target all $design
make_wrapper -files $design -top -import
set_property top radar_system_wrapper [current_fileset]
update_compile_order -fileset sources_1
set_property STEPS.WRITE_BITSTREAM.TCL.PRE [file join $root scripts compress_bitstream.tcl] [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Radar implementation failed"}
open_run impl_1
set reports [file join $root build reports]
file mkdir $reports
report_timing_summary -file [file join $reports timing.rpt]
report_utilization -file [file join $reports utilization.rpt]
report_drc -file [file join $reports drc.rpt]
report_route_status -file [file join $reports route.rpt]
report_io -file [file join $reports io.rpt]
foreach delay {max min} {
    set slack [get_property SLACK [get_timing_paths -delay_type $delay -max_paths 1]]
    if {$slack eq "" || $slack < 0} {error "Timing failed: $delay slack $slack"}
}
file copy -force [file join $build acoustic_radar.runs impl_1 radar_system_wrapper.bit] [file join $root build system.bit]
exit
