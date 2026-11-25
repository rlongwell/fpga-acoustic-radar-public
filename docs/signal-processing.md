# From microphone samples to a bearing

The guitar demo and desktop compass use two stages. The FPGA measures how similar each pair of microphone signals is over a range of time shifts. The desktop asks which arrival direction best explains the collection of measurements. [Project overview and demo](../README.md)

## Synchronous capture

Six INMP441 microphones share the I²S bit clock and word select. Each has its own data line, so the receiver samples the same 24-bit slot on all six channels. At 48 kHz one sample spans about 20.8 µs. For the nominal 91.44 mm M3–M6 baseline, a wave traveling along that baseline at 343 m/s takes about 267 µs to cross it, or about 13 samples. This example explains the scale of the delay. The solver uses each pair’s coordinates and the configured air temperature. [I²S receiver](../rtl/i2s_six.v) · [Array dimensions and channel order](hexagon.md)

## Pairwise correlation in hardware

The FPGA differences adjacent samples, scales the result, and accumulates a correlation over 4,096 frames (about 85 ms). For each of the 15 unique pairs it tests offsets from −32 through +32 samples. The result is a profile of 65 scores per pair plus six channel energies. Keeping the complete profiles lets the host evaluate directions even when a pair has a broad peak or several plausible offsets. [Correlator RTL](../rtl/correlator.v) · [Window format and register map](radar.md#rtl-and-uart-interface)

## Geometry and confidence on the desktop

For each horizontal bearing from 0° through 359°, the solver projects the microphone separations onto the incoming direction and converts those distances to sample delays. It interpolates between adjacent lag bins and combines evidence from active pairs. The dashboard uses 0° at M3 on the right, increasing counterclockwise. A one-degree search grid specifies how the estimate is displayed. Angular accuracy depends on the physical port coordinates, sound field and active channels. [Bearing solver and tracker](../radar/localization.py) · [Coordinate calibration](hexagon.md)

Echoes and sustained tones can match more than one direction. The level gate suppresses low-level windows. Optional filtering uses pair agreement and competing peaks to decide when to display an approximate direction or clear the marker. The plot estimates the bearing of one dominant source. The live screenshot shows the approximate marker with nominal geometry. [Reflection filtering](radar.md#reflection-rejection) · [Bench observations and FPGA self-test](../verification/radar_validation.md)

## Audio and bearing replay

The recorder timestamps each window against the FPGA sample counter and stores the six channels as a 24-bit WAV. Playback uses the stored bearing and geometry from that take. This keeps the strum aligned with its compass update even if network packets arrive unevenly. [Recording and replay](guitar_demo.md)
