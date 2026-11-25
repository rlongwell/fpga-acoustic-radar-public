# Digilent Zybo Z7-20 (xc7z020clg400-1), standard Pmod JE.
# Physical JE socket pins below are distinct from FPGA package pins.
# i2s_sck and i2s_ws must be RTL outputs; mic*_sd must be RTL inputs.
# This file assigns pins only. Define the fabric clock, clock enables and
# timing constraints appropriate to the eventual I2S controller in its project.
set_property -dict { PACKAGE_PIN V12 IOSTANDARD LVCMOS33 SLEW SLOW } [get_ports {i2s_sck}] ; # JE pin 1, OUT, BCLK
set_property -dict { PACKAGE_PIN W16 IOSTANDARD LVCMOS33 SLEW SLOW } [get_ports {i2s_ws}]  ; # JE pin 2, OUT, LRCLK
set_property -dict { PACKAGE_PIN J15 IOSTANDARD LVCMOS33 } [get_ports {mic1_sd}] ; # JE pin 3, IN, MIC1
set_property -dict { PACKAGE_PIN H15 IOSTANDARD LVCMOS33 } [get_ports {mic2_sd}] ; # JE pin 4, IN, MIC2
set_property -dict { PACKAGE_PIN V13 IOSTANDARD LVCMOS33 } [get_ports {mic3_sd}] ; # JE pin 7, IN, MIC3
# Uncomment after adding the top-level input and fourth microphone:
# set_property -dict { PACKAGE_PIN U17 IOSTANDARD LVCMOS33 } [get_ports {mic4_sd}] ; # JE pin 8, IN, MIC4 optional
# JE pins 5/11 are GND; JE pins 6/12 are +3.3 V. Neither gets an XDC constraint.
# JE pins 9 (T17) and 10 (Y17) are unused by this design.
