# Run from a scratch directory: vivado -mode batch -nolog -nojournal -source /path/to/check_vivado.tcl
# This fixture tests pin assignment only. It is not an I2S controller. No bitstream is generated.
set constraint_dir [file normalize [file join [file dirname [info script]] .. constraints]]
set xdc [file join $constraint_dir zybo_z7_20_je_inmp441.xdc]
set f [open $xdc r]
set constraints [read $f]
close $f
foreach count {3 4 6} {
    set mode [file normalize [file join [pwd] vivado_je_pincheck_${count}mic]]
    file mkdir $mode
    set rtl [file join $mode je_pincheck.v]
    set f [open $rtl w]
    set inputs [lrange {mic1_sd mic2_sd mic3_sd mic4_sd mic5_sd mic6_sd} 0 [expr {$count - 1}]]
    set rtl_inputs [join $inputs ", "]
    set rhs [join [lrange $inputs 1 end] " ^ "]
    puts $f "module je_pincheck(input wire $rtl_inputs, output wire i2s_sck, i2s_ws);"
    puts $f "assign i2s_sck = mic1_sd; assign i2s_ws = $rhs; endmodule"
    close $f
    if {$count == 4} {
        set variant [file join $mode four_mic.xdc]
        set edited [regsub -line {^# (set_property .*mic4_sd.*)$} $constraints {\1}]
        if {$edited eq $constraints} {error "Optional mic4_sd constraint not found"}
        set f [open $variant w]
        puts -nonewline $f $edited
        close $f
    } elseif {$count == 6} {
        set variant [file join $constraint_dir zybo_z7_20_je_inmp441_6mic.xdc]
    } else {
        set variant $xdc
    }
    read_verilog $rtl
    read_xdc $variant
    synth_design -top je_pincheck -part xc7z020clg400-1
    set expected {i2s_sck V12 OUT i2s_ws W16 OUT mic2_sd H15 IN}
    if {$count == 6} {
        lappend expected mic1_sd V13 IN mic3_sd J15 IN
    } else {
        lappend expected mic1_sd J15 IN mic3_sd V13 IN
    }
    if {$count >= 4} {lappend expected mic4_sd U17 IN}
    if {$count == 6} {lappend expected mic5_sd T17 IN mic6_sd Y17 IN}
    foreach {port loc dir} $expected {
        set pin [get_ports $port]
        set found [list [get_property PACKAGE_PIN $pin] [get_property IOSTANDARD $pin] [get_property DIRECTION $pin]]
        if {$found ne [list $loc LVCMOS33 $dir]} {error "$port: expected $loc LVCMOS33 $dir; got $found"}
        if {$dir eq "OUT" && [get_property SLEW $pin] ne "SLOW"} {error "$port: unexpected SLEW"}
        puts "JE CHECK $count $port $found"
    }
    place_design
    report_drc -checks {UCIO-1 NSTD-1} -file [file join $mode pin_drc.txt]
    set f [open [file join $mode pin_drc.txt] r]
    set report [read $f]
    close $f
    if {![regexp -nocase {Checks found:\s+0} $report]} {error "Pin / standard DRC did not pass: $report"}
    puts "JE CHECK $count placed; UCIO-1 and NSTD-1: zero violations"
    close_project
}
