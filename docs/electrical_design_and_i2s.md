# Electrical design and I²S timing

The Zybo Z7-20 PL is the clock master. JE is a standard 3.3 V GPIO Pmod. JE1 and JE2 drive the shared SCK and WS nets. Each module drives only its own FPGA input on JE3, JE4 or JE7 (JE8 for MIC4). All L/R pins are wired to GND and all microphones transmit in the same left time slot, so tying SD outputs together would create contention. No MCLK, level shifter, microphone amplifier, separate enable wire, or separate supply is needed for a working six-terminal INMP441 breakout. The bare IC has a CHIPEN pin; this design relies on the module enabling it internally. The exact module implementation is still to be inspected.

## Supply and local components

- **3.3 V only.** INMP441 VDD range is 1.62–3.63 V; its input absolute limit is −0.3 V to the lower of VDD + 0.3 V or 3.63 V. Design for normal 0–3.3 V levels. Do not use a 5 V rail, 5 V scope/analyzer drive, or active SCK/WS while the module is unpowered. At 3.3 V the datasheet lists 2.2 mA typical and 2.5 mA maximum in normal mode under its stated conditions. Budget about 7.5 mA for three or 10 mA for four bare ICs at that maximum, plus module extras and SD pull-down current. One 100 kΩ draws at most about 33 µA when its SD is high. This is a small JE load; the board's total power budget still applies.
- **C1–C4: 100 nF (0.1 µF), X7R or better.** Use one local VDD-to-GND bypass at every microphone, preferably right at the chip on the module; on a retrofit place across the module VDD/GND pads or on a small local adapter with minimum loop length. Omit the external capacitor if an appropriate local bypass is verified. Do not treat a distant breadboard capacitor as equivalent.
- **R1–R4: one 100 kΩ from each independent SD to GND.** TDK recommends a pull-down to discharge SD when its output goes high impedance. Install it physically on the private SD row or near the receiver, with a short ground connection. If the module already provides a verified equivalent on that SD net, omit the external one. Keep FPGA input pulls off/default; design the receiver to ignore high-impedance intervals, whose voltage may decay slowly through 100 kΩ on jumper wiring. The resistor is a shunt, never in series.
- **What is known about the EGSCST PCB.** The description and public search did not yield a traceable manufacturer schematic, parts list or exact revision photo for this kit. Similar circular boards exist, but their photographs do not prove the pad order, capacitor value, SD pull-down or CHIPEN strap on these boards. Inspect both sides and trace an unmarked capacitor to VDD and GND with power removed. Trace a suspected pull-down to SD and GND and measure with the module isolated; an in-circuit reading can be affected by parallel paths or the IC. Use supplier documentation or isolated component measurement for a value that cannot be established visually. If still uncertain after correct pad identification, provision the external bypass and pull-down. Check for an unexpected fixed-high L/R strap before connecting it to ground.

## Fanout and jumper length

Each clock output drives three (optionally four) high-impedance inputs in parallel. Capacitive load and the quality of the signal return matter more than static current or the nominal clock rate. Digilent shows **200 Ω already in series on each JE GPIO**; start with no extra series resistor or termination. The XDC selects slow slew on the clock outputs. As a rough illustration only, 200 Ω into an assumed lumped 100 pF gives τ ≈ 20 ns and a 10–90% transition of ≈ 44 ns before including driver or transmission-line effects. The actual wiring capacitance is unknown; this is not a timing signoff. Keep leads as short as practical (start around 5–10 cm where possible), use a compact fanout, keep branch stubs short and similar, and route SCK and WS next to return conductors. Bring up on short leads first. Treat approximately 20 cm end-to-end Dupont wiring as a bench trial; validate at the farthest module and again with all modules attached. Look for monotonic edges, no double crossing, legal high/low levels and SD settling before capture. If it fails, shorten and secure the harness and improve paired grounds; consider a buffered fanout only if measurements show it is needed.

## Clocking and capture

| Quantity | Target or check |
| --- | --- |
| Sample rate / word select | 48.000 kHz; period ≈ 20.833 µs |
| Serial bit clock | 3.072 MHz; period ≈ 325.52 ns; ideal 50% high/low ≈ 162.76 ns each |
| Stereo frame | 64 SCK cycles; 32 with WS low and 32 with WS high |
| Left word | WS low, 24 bits, two's-complement, MSB first; one SCK of I²S delay |
| Right word | WS high, all three left-selected outputs released |
| Source timing to check | TDK Table 3: SCK 0.5–3.2 MHz, period ≥312 ns, high/low ≥50 ns; WS 7.8–50 kHz, setup ≥0 ns and hold ≥20 ns at the microphone |

Drive WS transitions on SCK falling edges. At the first rising SCK edge that sees WS go low, detect the frame phase; capture bit 23 at the **next** rising edge, then capture down to bit 0 on consecutive rising edges, in parallel from each SD input. Use a suitably timed sampling point in the FPGA implementation and verify the return delay through the harness. SD releases after the LSB; ignore remaining bit times and the right slot. See the [timing drawing](../wiring/i2s_left_slot_timing.svg). This is standard I²S with a 24-bit payload in a 32-bit slot; it is not left-justified or a 48-clock frame.

On first power-up the datasheet specifies zero output for the first 2¹⁸ SCK cycles: allow approximately 85.3 ms (4,096 complete frames) of valid clocks, then start on the next left word. After a clock-stop standby interval, allow at least 2¹⁴ SCK cycles (about 5.33 ms) after restart, then start on a frame boundary. The shared clocks provide common framing for all modules; channel response and actual alignment have not been measured here. The pin XDC does not generate clocks or constrain a finished receiver. If using the Zybo's 125 MHz PL clock, a single integer divider does not produce exactly 3.072 MHz; verify both average frequency and per-cycle timing in the eventual design.

## References

- [Digilent Zybo Z7 reference manual](https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf), board callout 8, §16, Fig. 16.1, Table 16.1 and §16.1.
- [Digilent Zybo-Z7-Master.xdc](https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc), JE and system-clock sections. This is the Zybo Z7 file.
- [Digilent Zybo Z7 board schematic, rev. D.1](https://files.digilent.com/resources/programmable-logic/zybo-z7/zybo-z7-d1-sch.pdf), sheet 1: JE power/ground, 200 Ω resistors and protection arrays.
- [TDK/InvenSense DS-INMP441-00, rev. 1.1](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf), Tables 1–4 and 6, Fig. 1, pp. 10–13 and p. 15. The legacy URL may redirect; [this distributor-hosted copy of the same manufacturer datasheet](https://s3.amazonaws.com/snapeda/datasheet/INMP441ACEZ-R7_InvenSense.pdf) contains the consulted tables and figures.
