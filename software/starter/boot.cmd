# The reference FSBL initializes the Zynq PS and 100 MHz FCLK0.
# Program the PL first; start Linux only after all three boot inputs load.
if fatload mmc 0:1 0x10000000 system.bit && fpga loadb 0 0x10000000 ${filesize}; then
    if fatload mmc 0:1 0x02000000 uImage && fatload mmc 0:1 0x04000000 radar.ramdisk && fatload mmc 0:1 0x01f00000 radar.dtb; then
        setenv bootargs 'console=ttyPS0,115200 rdinit=/init zybo.profile=radar clk_ignore_unused'
        bootm 0x02000000 0x04000000 0x01f00000
    fi
fi
echo Failed to start acoustic radar. Check the radar card and reboot.
