# Six microphones on standard Pmod JE, Digilent Zybo Z7-20 (xc7z020clg400-1).
# Use this JE XDC by itself for the six-mic variant.
# The RTL must expose two output clocks and six independent SD inputs.
set_property -dict { PACKAGE_PIN V12 IOSTANDARD LVCMOS33 SLEW SLOW } [get_ports {i2s_sck}] ; # JE pin 1, OUT, BCLK
set_property -dict { PACKAGE_PIN W16 IOSTANDARD LVCMOS33 SLEW SLOW } [get_ports {i2s_ws}]  ; # JE pin 2, OUT, LRCLK
set_property -dict { PACKAGE_PIN V13 IOSTANDARD LVCMOS33 } [get_ports {mic1_sd}] ; # JE pin 7, IN, MIC1
set_property -dict { PACKAGE_PIN H15 IOSTANDARD LVCMOS33 } [get_ports {mic2_sd}] ; # JE pin 4, IN, MIC2
set_property -dict { PACKAGE_PIN J15 IOSTANDARD LVCMOS33 } [get_ports {mic3_sd}] ; # JE pin 3, IN, MIC3
set_property -dict { PACKAGE_PIN U17 IOSTANDARD LVCMOS33 } [get_ports {mic4_sd}] ; # JE pin 8, IN, MIC4
set_property -dict { PACKAGE_PIN T17 IOSTANDARD LVCMOS33 } [get_ports {mic5_sd}] ; # JE pin 9, IN, MIC5
set_property -dict { PACKAGE_PIN Y17 IOSTANDARD LVCMOS33 } [get_ports {mic6_sd}] ; # JE pin 10, IN, MIC6
# All eight JE GPIOs are used. JE5/11 are GND and JE6/12 are 3.3 V.
