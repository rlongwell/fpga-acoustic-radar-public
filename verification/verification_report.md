# Electrical and documentation verification

**Design 1.0 · 2026-11-15 · Zybo Z7-20 / XC7Z020-1CLG400C**

Status: **Document and tool checks passed. Physical breakout identification and bench validation are pending.** No hardware was powered, probed, programmed or used to capture samples for this package.

| Check | Result and basis |
| --- | --- |
| Board and connector | Digilent's Zybo Z7 reference manual names JE as the standard PL Pmod in Table 16.1; the dedicated Zybo Z7 master XDC was used. No original Zybo pin definitions were used. |
| JE orientation | Fig. 16.1 of the manual shows the front of the female connector with PCB below: pins 6/12 left, pin 1 top right, pin 7 below it. Fig. 5 and §5.2 of the Pmod spec support the host row convention. The board locator was checked against Digilent's board imagery: JE is at the left end of the switch-side Pmod row near the USB host corner. The drawing is explicitly a female mating-face view; the rear face of the mating plug would be mirrored. |
| Power and ground | Digilent reference manual §16 and its board schematic identify JE5/11 as GND and JE6/12 as a common 3.3 V rail. KiCad XML shows these as separate networks, with every VDD on +3V3, return and L/R on GND, and no 5 V network. The actual plug and harness still require a continuity/polarity check. |
| Pin map and FPGA direction | The manual and master XDC agree that JE1 V12 and JE2 W16 can drive the two shared clocks. JE3 J15, JE4 H15, JE7 V13 and optional JE8 U17 are FPGA inputs in the base design. The separate [six-mic variant](../docs/six_microphone_breadboard.md) adds FPGA inputs on JE9 T17 and JE10 Y17. Both variants use 3.3 V logic and unique package pins. |
| SD isolation and left selection | Netlist contains four distinct SD nets, each with one driver, one FPGA input and one shunt resistor. With U4 omitted there are three connected SD nets. L/R is grounded on each module; TDK Table 6 and Fig. 9 confirm the left selection. |
| Passives and fanout | TDK pp. 11 and 15 support 100 kΩ from each SD to GND and 100 nF X7R locally across each supply. KiCad netlist has the correct values and endpoints. Digilent manual §16.1 and rev. D.1 schematic sheet 1 support the onboard 200 Ω JE series resistors. No additional clock resistors are called for initially. The actual board loading, 20 cm jumper behavior and the four-module clock fanout require scope checks. |
| Timing | TDK Table 3 and Figs. 1, 8 and 9 were checked. The 3.072 MHz / 48 kHz plan is within the stated frequency limits; it uses 64 SCK per stereo frame. It captures 24 bits after the I²S one-cycle offset. Long-wire signal timing and FPGA receive margins were not measured. |
| Cross-file agreement | KiCad 7.0.11 opened the native file in its schematic export commands and generated PDF, SVG and an XML netlist. Python validated exact net membership and DNP flags against the connection table and XDC and compared the wiring endpoints and JE mating-face positions. The latest schematic and all five wiring print pages were also rendered and visually inspected. This is a netlist-based electrical check; KiCad 7.0.11's CLI did not expose ERC. |
| Vivado integration | Vivado 2024.2 synthesized and placed a pin fixture on `xc7z020clg400-1` for the three-, four-, and six-microphone configurations. Each assignment, direction, and standard matched. SCK and WS used SLOW slew. `UCIO-1` and `NSTD-1` passed for all three configurations. These runs establish pin acceptance. Clock waveforms with six physical loads still need a bench check. |

### Physical checks still needed

- Obtain clear, matched close-ups of both sides of one actual EGSCST module. Include all six pads, silkscreen, visible passives and a landmark common to both sides. If modules have different revisions, obtain a photo pair for each.
- Map the pad labels, verify continuity through the soldered headers, and check for onboard VDD-to-GND bypass, an SD-to-GND pull-down, or any unexpected L/R strap. A photo does not establish the value of an unmarked component; confirm value or fit the external part when needed. If the module has an exposed or unstrapped CHIPEN, stop and recheck the exact board variant.
- With the harness unpowered and independent of the Zybo, check JE orientation at the plug, power and ground isolation, and isolation between each SD and the other SD/clock nets. Verify the 3.3 V polarity at every microphone before enabling clocks, then scope SCK, WS and SD as described in the [assembly guide](../docs/assembly_guide.md).

### Reproduce the checks

From this project directory, run `python3 verification/check_connectivity.py` (standard library only). To also verify against Digilent's file, pass `--master-xdc /path/to/Zybo-Z7-Master.xdc`. The reviewed [official raw XDC](https://raw.githubusercontent.com/Digilent/digilent-xdc/master/Zybo-Z7-Master.xdc) had SHA-256 `63a843355f360ce2594cec40952c46fd9498002e0044a18a8b711ee1bdced478`. After changing the schematic, refresh the netlist with `kicad-cli sch export netlist --format kicadxml -o schematic/zybo_je_inmp441.net.xml schematic/zybo_je_inmp441.kicad_sch`.

Run `vivado -mode batch -nolog -nojournal -source /absolute/path/to/verification/check_vivado.tcl` from a scratch directory. The script creates local fixture directories for three, four, and six microphones. See [the captured pin results](vivado_pin_check.txt).

Sources: [Digilent Zybo Z7 reference manual](https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf), [Digilent Zybo-Z7-Master.xdc](https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc), [Digilent Pmod interface specification 1.3.1](https://digilent.com/reference/_media/reference/pmod/pmod-interface-specification-1_3_1.pdf), [Digilent product imagery](https://digilent.com/shop/zybo-z7-zynq-7000-arm-fpga-soc-development-board/), [Digilent board schematic, D.1](https://files.digilent.com/resources/programmable-logic/zybo-z7/zybo-z7-d1-sch.pdf), and [TDK/InvenSense INMP441 datasheet](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf).
