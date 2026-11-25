# One-time boot from the dedicated radar bundle. The shared default stays available.
if part uuid mmc 0:2 rootuuid && fatload mmc 0:1 0x02000000 zImage && fatload mmc 0:1 0x03000000 profiles/radar/system.dtb && fdt addr 0x03000000 && fatload mmc 0:1 0x10000000 profiles/radar/system.bit; then
    # Keep the shared Zynq PS configuration and set FCLK0 to its 100 MHz profile.
    if setexpr.l radar_clk *0xf8000170 '&' 0xfc0fffff && setexpr radar_clk ${radar_clk} '|' 0x00200000; then
        mw.l 0xf8000008 0x0000df0d
        mw.l 0xf8000170 ${radar_clk}
        mw.l 0xf8000004 0x0000767b
        if fpga loadb 0 0x10000000 ${filesize}; then
            echo FPGA bitstream: profiles/radar/system.bit
            echo Device tree: profiles/radar/system.dtb
            setenv bootargs "console=ttyPS0,115200 root=PARTUUID=${rootuuid} rootfstype=ext4 rw rootwait cma=32M uio_pdrv_genirq.of_id=generic-uio zybo.profile=radar"
            bootz 0x02000000 - 0x03000000
        fi
    fi
fi
echo Radar boot failed. Reset for the normal shared SD profile.
