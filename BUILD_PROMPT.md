# Build the six-microphone acoustic radar for Zybo Z7-20

Extend the existing six-INMP441 wiring project in this directory into an end-to-end acoustic direction display. Follow the workspace's FPGA project conventions. Deliver synthesizable RTL, the Vivado build, reproducible validation, deployable SD files, the Zybo UART bridge, and a PySide6 dashboard. Build and validate on the connected Zybo once the implementation passes timing.

## Hardware and capture

- Target the Digilent Zybo Z7-20, `xc7z020clg400-1`, with Vivado 2024.2. Use the verified six-microphone XDC in this repository.
- Drive SCK on JE1 and WS on JE2. In MIC1 through MIC6 order, connect the six separate SD lines to **JE7, JE4, JE3, JE8, JE9, JE10**. Every L/R pad is connected to the common ground. The harness uses JE5 for GND and JE6 for 3.3 V.
- The active array is the six-port protoboard hexagon. Use the labeled X/Y acoustic-port coordinates from [the hexagon guide](docs/hexagon.md) and allow temperature compensation. Keep the original 2 × 3 geometry available for the earlier breadboard.
- Derive the I²S timing from the 100 MHz FCLK0, with 3.072 MHz average SCK, 48 kHz WS, and 32 SCK periods per WS state. Capture the six signed 24-bit left samples together with the standard I²S one-bit delay. Discard the microphone startup interval and keep both WS states even though the receivers use the left slot.
- Implement windowed cross-correlation of the 15 channel pairs in programmable logic. Use a high-pass step, signed fixed-point samples, and lag bins from -32 through +32 at 48 kHz. Publish completed windows atomically with channel energies, frame count, dropped frames, and a sequence number.
- Provide a deterministic internal self-test with known per-channel delays [2, 1, 0, 4, 3, 2]. Verify all 15 expected peaks. Internal test packets must carry their own source label.
- Document signed lag conventions and scale, internal timing reports, the validated bitstream hash, and any external microphone checks still pending.

## Build and deploy

- Use the local Zybo board and Zybo file-transfer skills. Identify the active shared SD profile and use only the confirmed USB UART device. Release UART sessions between tools and preserve the existing profiles and boot defaults.
- Stage a complete radar payload on the board SD filesystem with the timing-checked bitstream, compatible DTB, one-time U-Boot script, ARM Linux bridge, and SHA-256 manifests. Publish with verified checksums, then boot that payload through U-Boot and confirm the PL register identity from Linux.
- Use the shared Linux kernel and a radar-specific UIO register map. Keep the live stream separate from the shell by running it as a bounded foreground program with a heartbeat and cleanup on disconnect. Stream telemetry at 115200 baud over the existing J12 USB UART. Send normalized int8 lag profiles, levels, counters, and CRC with each packet. Keep traffic within the connection's capacity.
- Validate RTL with a simulation of known 24-bit I²S words and known correlation lags. Check UART CRC handling, geometry, silence, and expected synthetic bearings in software. On the Zybo, verify timing-independent register identity, run the internal test, and capture real telemetry. Treat a known sound-source direction as a separate physical acceptance check.

## PySide6 dashboard

- Start the application with an executable `dashboard.sh`. Follow the workspace launcher and GUI preference skills. Use pinned dependencies, a project-local environment, dark gray by default, an accessible light theme toggle, and local settings.
- Have the dashboard connect and disconnect over UART, show all six channel levels, and display a 360-degree bearing plot. Identify live FPGA data and simulated demo data explicitly. Keep serial work out of the GUI thread.
- Steer with the selected geometry. For the hexagon, number the microphones clockwise from upper-left M1. For bearings, 0 degrees points right toward M3 and angles increase counterclockwise. For the 2 × 3 mode, 0 degrees points toward the far row and angles increase clockwise. Estimate horizontal bearing from the lag profiles and show no bearing when there is insufficient energy or conflicting evidence. This design estimates passive direction and has no distance measurement.
- Provide a short operator guide for one-time boot, rollback to the existing SD default, UART use, spacing entry, and microphone troubleshooting. Include the local and board-side artifact paths and name each check that was actually run.
