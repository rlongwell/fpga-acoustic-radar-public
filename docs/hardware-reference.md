# Acoustic radar hardware reference

## Board releases and recording

The [six-microphone release](../releases/six-mic-hexagon/) preserves the earlier radar profile and shared SD boot selector. `radar-profile.tar.gz` contains the bitstream, device tree, UART bridge, boot script and installer. `shared-boot-selector.tar.gz` contains the shared boot script and Linux profile selection tools. The separate `radar-stream-ethernet` ARM binary upgrades the original profile’s bridge to support wired Ethernet and USB UART. Its installed path is `/opt/zybo/radar/radar-stream`. Run `sha256sum -c SHA256SUMS` inside the release directory to verify the files. The [bench report](../verification/radar_validation.md) links the recorded captures and implementation reports.

The [six-channel recording release](../releases/six-mic-recording/) contains the deployed PCM-capable bitstream, DTB, bridge, boot script and installer. Use **Record take** below the compass on the Wi-Fi or Ethernet dashboard to save all six physical microphone channels and sample-aligned radar measurements. **Replay last take** plays the recording offline. Under **Audio**, choose **M1 only** or **All six mics** for replay and export. New WAVs and MP4 exports include time-of-day metadata for aligning phone footage. **Export MP4…** creates a radar clip with guitar audio for your editor. Takes are saved under `~/Videos/Acoustic Radar/`. Replay uses `gst-play-1.0`; MP4 export uses FFmpeg with libx264 and AAC. The [overhead guitar demo guide](guitar_demo.md) covers the clap sync, files, and shot list.

## Wiring references

The wiring uses 3.3 V logic, two shared clocks, and one SD input per left-selected microphone. Match the actual breakout labels and check polarity before powering up. The original three- and four-microphone diagrams remain available below.

The active protoboard uses the [six-microphone hexagon layout](hexagon.md). Viewed with the harness at upper right, GUI M1 is upper left and the microphones run clockwise. M1 feeds JE8 and rightmost M3 feeds JE10. The hexagon wiring diagram uses the dashboard’s M1–M6 labels. The dashboard plots 0° toward M3 and 270° between M4 and M5. [JE connector drawing](../wiring/six_microphone_hexagon_plug_in_guide.pdf) · [Six-microphone XDC](../constraints/zybo_z7_20_je_inmp441_6mic.xdc)

For the older **2 × 3** layout, use the [rectangular wiring drawing](../wiring/six_microphone_rewiring_guide.pdf) and [breadboard instructions](six_microphone_breadboard.md).

### Original three- and four-microphone wiring

1. Read the [assembly guide](assembly_guide.md) and use the [three-microphone wiring drawing](../wiring/wiring_three_microphones.svg).
2. Find JE and orient the plug using the [female mating face](../wiring/pmod_je_mating_face.svg). With the PCB below the socket, **pin 1 is upper right**. The upper row from left to right is 6–1; the lower row is 12–7.
3. Match microphone terminals by their verified labels. Use the [logic-level terminal guide](../wiring/inmp441_breakout_logical_pinout.svg) until an exact physical pad map has been established.

| Area | Files |
| --- | --- |
| Native schematic | [zybo_je_inmp441.kicad_sch](../schematic/zybo_je_inmp441.kicad_sch), [je_array.kicad_sym](../schematic/je_array.kicad_sym), [sym-lib-table](../schematic/sym-lib-table) |
| Schematic exports | [PDF](../schematic/zybo_je_inmp441.pdf), [SVG](../schematic/zybo_je_inmp441.svg), [PNG preview](../schematic/zybo_je_inmp441.png), [KiCad XML netlist](../schematic/zybo_je_inmp441.net.xml) |
| Wiring | [Five-page print set](../wiring/zybo_je_wiring_print_set.pdf), [three microphones SVG](../wiring/wiring_three_microphones.svg), [PNG preview](../wiring/wiring_three_microphones.png), [JE mating face](../wiring/pmod_je_mating_face.svg), [module logical terminals](../wiring/inmp441_breakout_logical_pinout.svg), [MIC4 expansion](../wiring/wiring_fourth_microphone.svg), [left-slot timing diagram](../wiring/i2s_left_slot_timing.svg) |
| Build and design | [Assembly guide](assembly_guide.md), [electrical design and I²S timing](electrical_design_and_i2s.md), [complete pin connection table](connection_table.csv), [bill of materials](../bom.csv) |
| Vivado 2024.2 | [Zybo Z7-20 JE XDC](../constraints/zybo_z7_20_je_inmp441.xdc) |
| Verification | [Report](../verification/verification_report.md), [connectivity checker](../verification/check_connectivity.py), [Vivado check script](../verification/check_vivado.tcl), [Vivado check output](../verification/vivado_pin_check.txt) |

Open the native schematic with KiCad 7 or newer; keep the symbol library and its table alongside the schematic. The design uses logical terminal names and intentionally has no breakout footprint. U4/R4/C4 are marked DNP for the three-mic build; when building four, use the connections shown but include the passive parts only as needed after inspection. The netlist includes the optional branch and carries DNP flags. For printed copies, choose landscape orientation and fit to page, or use the SVGs for large-format output.
