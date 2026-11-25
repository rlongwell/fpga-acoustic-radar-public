# Wi-Fi on the existing Zybo shared SD card

The installed Panda adapter enumerates as USB ID `0e8d:7610`. On the shared SD image, the `mt76x0u` driver creates `wlan0` and the saved network configuration starts association and DHCP at boot. The board joined the 5 GHz network at 5220 MHz during the bench check.

1. Power off. Leave **J10** (micro USB OTG) unplugged and install the adapter
   in **J11** (full-size USB-A). For host mode, Digilent specifies **JP2 fitted**
   and **JP1 open**. Keep **J12** connected to the PC for the initial console
   setup. Use a suitable 5 V supply at J17 with JP6 at WALL if the USB power
   input cannot support the additional adapter load.
2. Boot normally. Close the radar GUI if it is currently using the UART.
   Open the console with `zybo-uart`, sign in as usual, and run
   `zybo-wifi configure`. Enter the Wi-Fi name and password into the local
   console. Choose the default WPA2 option for a WPA2 or WPA2/WPA3 mixed
   network. Choose WPA3 only if the router is set to WPA3 only.
3. Run `zybo-wifi status`. Look for `wpa_state=COMPLETED` and an IPv4 address.
   If association works but no address appears, inspect
   `/var/log/zybo-wifi.log`. The config is saved in `/etc/zybo/wifi.conf`
   (root only); the service reconnects when the adapter is plugged in or after
   reboot. A router on the local subnet must provide DHCP and a usable route
   for internet access.

Verify wireless shell access from the PC with `ssh zybo-wifi`. To stream the radar over the same interface, run `./dashboard.sh --wifi`. The dashboard labels live wireless frames **Wi-Fi**. [Dashboard connection settings](radar.md#wi-fi-connection)

Recopying a factory shared image will replace this update. Rebuild with
`scripts/build_wifi_kernel.sh`, `scripts/build_wifi_modules.sh`, and
`scripts/build_wifi_tools.sh`; check the kernel's module ABI with `scripts/check_wifi_kernel.py`, and package Wi-Fi tools
with `scripts/package_wifi_tools.sh`. That package includes the host's
distribution-provided MediaTek firmware and regulatory database, verified by
the package manager and deployed over the physical console with SHA-256.
The MediaTek firmware and regulatory database are also embedded in the
kernel so USB discovery works before the SD root filesystem is mounted. The
Linux wireless driver applies the database rules for the configured country (US). Boot profile checks and kernel recovery do not require network
access.

To roll back from the board's USB console, first verify `/boot/zImage.pre-wifi`
is present, then copy it to a temporary file in `/boot` and rename the temp
file to `/boot/zImage`. Sync and reboot. If Linux won't start at all, restore the
same backup from another computer using the SD card's FAT partition. The
original and Wi-Fi kernels use separate module directories, so the original
modules remain available for rollback.
