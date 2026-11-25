# A first run on your own Zybo Z7-20

Follow the [wiring and startup steps](../README.md#try-it) first. The starter card runs the six-microphone compass over USB with a dedicated Linux console. The project’s existing network-enabled installation also supports six-channel audio recording and replay. [Network and recording setup](hardware-reference.md)

## What goes on the card

`./scripts/prepare-sd.sh` builds an ordinary disk-image file under `build/` on the PC. On the first run it fetches the 542 MiB **Zybo Z7-20 PetaLinux 2022.1** board support package (BSP) and checks its SHA-256. The helper caches the BSP for later runs. If you already have that release, use `RADAR_BSP=/path/to/Zybo-Z7-20-Petalinux-2022-1.bsp ./scripts/prepare-sd.sh`. [Digilent release](https://github.com/Digilent/Zybo-Z7/releases/tag/20/Petalinux/2022.1-1) · [Image builder](../scripts/prepare-sd.sh)

The boot partition contains the Digilent first-stage loader and U-Boot in `BOOT.BIN`, the radar design in `system.bit`, an ARM Linux kernel, the radar device tree, a small RAM filesystem and a U-Boot script. The bitstream, device tree and microphone bridge come from the checksum-verified [six-mic recording release](../releases/six-mic-recording). U-Boot programs the FPGA before starting Linux. The RAM filesystem starts the radar UIO driver and a local USB console. Eject the card after writing it and select the **SD** position printed at JP5. [Boot script](../software/starter/boot.cmd) · [Digilent Zybo Z7 reference manual](https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf)

## Check the board and wiring

On boot, the bridge runs its internal test pattern. A passing physical FPGA reports `RADAR-SELFTEST PASS 15 pairs`. This checks the correlator. To check the microphones, watch all six meters while playing broadband sound around the array. Measure the acoustic port positions and enter them in the dashboard for a calibrated geometry. [Physical layout and calibration](hexagon.md)

To run the self-test on demand, close the dashboard to free the serial port. After the first dashboard launch has created the Python environment, run:

```sh
.venv/bin/python scripts/board.py self-test --port auto
```

`--port auto` selects interface 01 of a connected Digilent USB cable. If you have several boards or a different USB identifier, list the serial ports and pass the UART device for your board explicitly:

```sh
ls -l /dev/serial/by-id/
./dashboard.sh --port /dev/ttyUSB1
```

`/dev/ttyUSB1` is an example. If Ubuntu reports permission denied, add your account to `dialout` with `sudo usermod -aG dialout "$USER"`, then log out and back in. Use a data-capable cable at J12 and close other serial terminals before opening the dashboard. If the board reports a good self-test but one meter stays quiet, power down and trace that microphone’s SD, power and clock wires. [Silent-channel checks](hexagon.md#checking-a-silent-channel)

## Build the FPGA yourself

Install **AMD Vivado 2024.2** for Linux with Zynq-7000 device support. From a shell with Vivado on `PATH`, run:

```sh
./build.sh
./scripts/prepare-sd.sh --built
```

The build targets `xc7z020clg400-1`, checks routed setup and hold timing, and writes `build/system.bit` and its checksum. The second command verifies that checksum and packages your build in `build/radar-sd.img`. Restore that image to the spare card as in the README. Use `VIVADO=/path/to/vivado ./build.sh` to select another installation of the same version. This design uses Digilent’s Zybo Z7-20 board preset **1.2**, included under its original MIT license. [Upstream board files at the included revision](https://github.com/Digilent/vivado-boards/tree/d8d43ed9f3f7e367ee3de82782ed601d88305677/new/board_files/zybo-z7-20/A.0)

## Validation

The released radar hardware and microphone bridge were exercised on a physical Zybo using the original shared Linux installation. The standalone starter image was assembled on Ubuntu 24.04. Its packaged kernel, device tree, UIO driver, console login and logout were checked under Zynq emulation. A cold boot of this new image on a physical board is still pending. [Physical bench evidence](../verification/radar_validation.md)
