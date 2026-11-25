# Mic data enters the I2S capture domain through the asynchronous input pipeline.
# SCK is derived from FCLK0. The return data is sampled inside its stable half-cycle.
set_false_path -from [get_ports {mic1_sd mic2_sd mic3_sd mic4_sd mic5_sd mic6_sd}] \
    -to [get_cells -hier -filter {NAME =~ */sd_meta_reg*}]
