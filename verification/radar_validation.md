# Acoustic radar validation

## Six-channel recording and filming view · 2026-11-19

The recording profile booted from SD over a power-independent Wi-Fi link. Vivado 2024.2 reported 1.440 ns worst setup slack, 0.029 ns worst hold slack and zero DRC errors. The prior radar profile and bridge were backed up on the card. The installed bitstream SHA-256 is `2f8db1a95c71a3f9fa7e59a8de6ed2da4f2c26c9eb9942b92c49734ea28cf1d7`. The FPGA self-test passed all 15 pairs and the new UIO capability read PCM6. Both HDL simulations passed, including six-channel word order, signed bits, ring wrap, exact window sample count and AXI backpressure.

- The desktop **Record take** and **Stop recording** buttons produced 691,200 continuous 24-bit samples per mic (14.4 s). All six channels had distinct waveforms. The mono edit track matched M1 sample for sample. The FPGA drop counter stayed zero. The live view recorded 164 radar windows and skipped three window sequence numbers; the acquisition contained all PCM blocks. One M6 sample reached negative full scale. The final network reader retains batched radar windows while recording, covered by the coalesced-packet regression test. [Take measurements](bench/guitar-view/wifi-take.json)
- **Replay last take** played and paused the same take in the GUI. **Export MP4…** produced 432 H.264 frames at 1080 × 1080, 30 fps and mono AAC at 48 kHz. Both tracks ran for 14.4 s. The export was decoded and visually inspected. The phone video and its alignment were outside this bench test. [Export metadata](bench/guitar-view/wifi-export.json)
- On the final PC Ethernet → Zybo Wi-Fi path, the running dashboard SSH socket used the wired DHCP address, packets were observed on physical `enp3s0`, and the board returned them on `wlan0` with `eth0` carrier 0. The PCM reader received another 241,152 contiguous samples per microphone over that route. The PC's direct RDP session remained connected.
- In the earlier right–mute–left playing check, accepted bearings in the selected right window had a median of 12° (156 readings), the mute window had zero accepted readings (43 windows), and the left window had a median of 181° (105 readings). These were live displayed values during the user's test. The camera did not independently timestamp source positions. [Observed directions and gaps](bench/guitar-view/right-mute-left.tsv)


## Wireless telemetry — 2026-11-19

The live dashboard opened its own pinned-key SSH session from the PC at `192.168.1.222` to the board at `192.168.1.21`. The PC used `wlo1`, and the Zybo accepted the session and routed its replies over `wlan0`. The Panda adapter used the `mt76x0u` driver on 5 GHz. A fresh SSH login reached the same board over Wi-Fi. The Ethernet interface check rejected that wireless SSH connection as expected.

With both network links available, the Wi-Fi dashboard showed windows 240 through 322 over approximately seven seconds. The desktop observer saw 76 distinct updates. At the end, all six microphone channels were active and the FPGA reported zero dropped frames. The dashboard saved Wi-Fi for subsequent launches. All 48 software tests and the Verilator regression passed.

After the Ethernet cable was unplugged, two fresh SSH checks reported Ethernet carrier 0 and wireless carrier 1. The same desktop SSH connection stayed established. The dashboard advanced from window 2193 to 2275, with 74 distinct updates observed in seven seconds, six active microphone channels and zero reported FPGA drops. An independent wireless SSH login and two internet pings also succeeded with the cable out.

## Wired telemetry and compass layout — 2026-11-19

The running desktop connected from `10.77.78.1` to the Zybo at `10.77.78.2:22`. The remote SSH endpoint matched a local address on `eth0`. After switching the desktop to Ethernet, the USB UART had no owner. In a six-second observation, the desktop displayed all 72 consecutive FPGA window numbers from 326 through 397. The final reading showed six active microphones and zero FPGA drops.

During the transport comparison, 72 wired snapshots arrived with a median interval of 85.8 ms. On the same acquisition, the existing USB UART dashboard displayed 36 updates with a median interval of 203.2 ms. These measurements describe update cadence. Measuring acoustic onset to visible bearing requires a synchronized sound and display recording.

Offscreen regressions checked chart position and dimensions across silence, the closed level gate and a tracked sound at three widths in both themes. All 47 Python tests and the Verilator regression passed.

## Radar as the saved SD boot profile — 2026-11-19

The shared loader and profile selector now support the installed radar bitstream and DTB. The board selected radar using `zybo-profile select radar`. A normal Linux reboot, with no serial input during U-Boot, loaded `profiles/radar/system.bit` and `profiles/radar/system.dtb`. Linux reported current profile `radar` and next boot `radar`, and the PL returned ABI `00010000`. [Unattended boot log](bench/radar-default/unattended-boot.log) · [Activation and readback](bench/radar-default/activation.log)

The USB uploader verified `/root/radar-default-f9f2b158a86f.tar.gz` with SHA-256 `f9f2b158a86f5fa5f083e164981b52c6b4f375513acce0c501ca87174a03cd06`. The previous boot script and selection are backed up at `/boot/before-radar-default.nOgbqf/`, with previous Linux selector files at `/root/before-radar-default.OrAwbO/`. [Transfer record](bench/radar-default/upload.log)

After reboot the FPGA passed all 15 internal pair checks. Twelve live windows had zero FPGA drops, activity on M1–M5 and a quiet M6. The PC dashboard reconnected to the physical UART with the clockwise hexagon layout. [Self-test](bench/radar-default/self-test.log) · [Live packets](bench/radar-default/live.log) · [Dashboard](bench/radar-default/live-dashboard.png)

## Clockwise channel numbering from the component-side photo

With the harness at lower left, channels 1–6 run clockwise from upper left. The bottom pair is M4/M5. Earlier hexagon commissioning entries below use the position names in effect during those tests. The dashboard migrated the saved coordinates and used the new order for the plot, calibration editor and steering calculations. The FPGA uses the existing six-channel JE assignments.

The user reported music from the bottom side. In 50 CRC-checked live windows the FPGA dropped zero input frames, M1–M5 were active throughout and M6 had zero energy in 49 windows. All 50 windows passed the saved −17 dB gate. The unfiltered solver accepted 24 bearings with a circular mean of 309.5°. A source centered below M4/M5 would be 270°; the phone position and port coordinates were not independently measured. All 42 host tests and the Verilator regression passed. [Capture](bench/hexagon-clockwise/phone-bottom.ar1) · [Analysis](bench/hexagon-clockwise/phone-bottom.json) · [Live display](bench/hexagon-clockwise/live.png)

## Live hexagon commissioning — 2026-11-19

The connected Zybo loaded the six-channel swapped bitstream from `/boot/profiles/radar/system.bit`. The SD checksum was `ba447e3f35c22583d6bcd3e24dd233225c7cb48f6484ff6ac6740f0d21288f2a`. The UART uploader verified the staged archive at `/root/acoustic-radar-ba447e3f35c2-1795079978.tar.gz` with SHA-256 `897bffebfe22cbd78411fe0660342db93cbb767285f9d91a6693b452c245578d`. U-Boot loaded the radar profile for this session. The saved default is `hash` and the Wi-Fi-enabled kernel is `6.6.40-dfx-hash-wifi`. [Deployment and internal self-test](bench/hexagon/deploy.log) · [Board status after boot](bench/hexagon/board-status.log)

| Check | Result |
| --- | --- |
| FPGA internal stimulus | Passed all 15 pair correlations. The self-test bypasses the microphone leads. |
| External channels, initial 50 CRC-checked live windows | Only M3 and M4 exceeded the activity threshold. M1, M2, M5 and M6 reported zero energy in every window. The FPGA reported zero dropped input frames. [Capture analysis](bench/hexagon/ambient.json) |
| Phone music on the M5/M6 side, 50 further live windows | Same two active channels, zero dropped input frames. Relative array level ranged from −21.7 to −19.9 dB. Replaying with the gate bypassed produced zero valid bearings. A centered source on that side would be 270°. Its physical bearing could not be verified. [Raw packets](bench/hexagon/phone-m5-m6.ar1) · [Analysis](bench/hexagon/phone-m5-m6.json) |
| Later 50-window repeat | All six channels had nonzero energy. M1 through M6 crossed the activity threshold in 50, 50, 50, 45, 34 and 41 windows. The median array level was −27.5 dB. With the display gate bypassed, the strongest steering score on any window was 0.028 (acceptance floor 0.12). All pair profiles involving M2 quantized to zero throughout this repeat, despite M2 having nonzero energy. These observations establish intermittent channel activity, not six verified audio signals. [Raw packets](bench/hexagon/recheck.ar1) · [Analysis](bench/hexagon/recheck.json) |
| Host geometry and display | Tested independently generated arrival times at 11 source angles, including 0°, 270° and wraparound. With synthetic six-channel data both unfiltered and Gentle-mode estimates passed the 3° tolerance. All 41 host tests and the Verilator regression passed. This tolerance describes the synthetic test. [Test log](bench/hexagon/test.log) |
| Live GUI | The dashboard ran on the real UART using the hexagon coordinates at 20 °C. The plotted layout and activity summary updated with incoming frames. A subsequent screenshot showed five active channels and a closed level gate. In 100 further GUI packets, four to six channels crossed the activity threshold, yet every ungated estimate reported weak directional signal. [Dashboard packet check](bench/hexagon/dashboard-check.json) · [Live screenshot](bench/hexagon/dashboard-live.png) |

The port coordinates are intended mounting positions. Physical port offsets, wiring continuity, and angular accuracy with a functioning array still require bench measurements. [Hexagon layout and channel-isolation procedure](../docs/hexagon.md)

## Six-microphone SD swap build — 2026-11-19

Upper-left MIC1 now enters on JE7/V13 and upper-right MIC3 on JE3/J15. The remap is in the six-microphone FPGA constraints, upstream of both channel energies and all 15 pair correlations. This build was completed on the PC. Programming the board and checking live microphone positions are pending.

- Vivado 2024.2 generated `build/system.bit` for `xc7z020clg400-1`. Its verified SHA-256 is `ba447e3f35c22583d6bcd3e24dd233225c7cb48f6484ff6ac6740f0d21288f2a`. The routed design has zero routing errors, +0.108 ns setup slack, and +0.033 ns hold slack. These timing results cover the constrained FPGA paths. [Timing](bench/reports/timing.rpt) · [Routing](bench/reports/route.rpt)
- The routed I/O report confirms all six SD inputs and both clock outputs use LVCMOS33. All eight package pins agree with the JE pin table, six-mic XDC and rendered wiring guides. Separate three-, four- and six-microphone pin fixtures passed placement and the UCIO-1/NSTD-1 checks. [Routed I/O](bench/reports/io.rpt) · [Pin fixtures](vivado_pin_check.txt)
- All 36 software tests passed. The Verilator regression passed for six I²S words, clock timing, 15 correlation peaks and snapshot banks. [Test log](bench/mic1-mic3-tests.log)
- The routed DRC lists 57 slice LUT-pair warnings (PDRC-132 through PDRC-146) and zero errors. The project build also repeats the prior board-preset DDR skew and read-only reset-parameter messages. The generated reset IP uses active-low external reset. [DRC](bench/reports/drc.rpt) · [Build log](bench/mic1-mic3-build.log)

## Original build and board tests — 2026-11-15

- Software tests decode checksum-verified telemetry, reject a corrupt packet, and validate synthetic bearings and silence.
- The Verilator test exercises the serial input I²S framing for all six sample words, SCK timing and WS transitions, all 15 correlation peaks, and the snapshot banks.
- The dashboard was rendered in both themes using its labeled demo.
- Vivado 2024.2 routed the design on `xc7z020clg400-1`. Worst setup slack was +0.152 ns and worst hold slack was +0.025 ns. Bitstream generation completed. [Original build log](bench/vivado.log)
- The UART uploader verified the deployment archive as `a1b945c0492d43d3bec224575c4bfbca682df15cce7f579acb2deaab8e282141`. The board installer and the boot preflight both verified the staged files. The board's `/boot/profiles/radar/system.bit` had SHA-256 `5f5bdcc15ed4f6a324e8faaac5ae8facf0f13b159677b5366c24409dc052f518`, matching that build. The UART bridge is installed at `/opt/zybo/radar/radar-stream`.
- U-Boot loaded the radar bitstream and DTB from the SD card. Linux booted the radar session, exposed the UIO device, and returned ABI `00010000` from the PL. The saved next boot profile was `hash`. [Boot evidence](bench/board-boot.log)
- The physical FPGA self-test passed all 15 expected correlation peaks, with zero dropped input frames. [Self-test evidence](bench/board-self-test.log)
- Twelve live windows passed transport checks. All reported zero dropped frames. Channels 1, 3, 4, 5, and 6 had nonzero activity. Channel 2 stayed at zero in all twelve windows. The software cannot identify whether this is the microphone, wiring, or the input path. [Live capture](bench/board-capture.log)
- The PySide6 dashboard opened a real UART session, displayed live channel levels, and released the serial console when closed. [Live dashboard capture](bench/dashboard-live.png)

A known physical sound-source bearing remains to be checked with the measured array spacing. When the Zybo is off, verify MIC2 VDD, GND, L/R and the SD wire to JE4. Swapping only the MIC1 and MIC2 SD leads at JE with power off can show whether the quiet reading follows the microphone path or stays on the JE4 input.

## Reflection rejection update

The desktop now uses robust pair agreement, competing-direction rejection, temporal confirmation, circular smoothing, a fading-power gate, and stale-data clearing. The normal view displays only the accepted lobe. An optional gray raw overlay preserves diagnostic access to the original response. These are host changes using the existing UART protocol and FPGA bitstream. The [operator guide](../docs/radar.md#reflection-rejection) gives the exact thresholds, research references and limits.

- **22 Python/Qt tests passed** using `.venv/bin/python -m unittest discover -s tests -v`. The tests include waveforms formed from the same broadband source arriving directly and as a delayed reflection, two equally strong directions, corrupt pair evidence, quiet MIC2 at the saved 36/55 mm geometry, noise, falling power, one-frame jumps, sustained direction changes, short clear onsets, duplicate frame redraws, wraparound, telemetry gaps and GUI settings. [Test log](bench/reflection-tests.log)
- The project test script also passed the existing Verilator I²S/correlation regression. Its system Python lacks Qt and skips four GUI tests; the separate virtual-environment run above executed those tests successfully. [Project test log](bench/reflection-full-tests.log)
- A **40-frame live baseline** had weak directional evidence; replay through the new filter accepted no sources. This confirms suppression of weak plotted shapes, not the physical identity of the sound. [CRC-protected baseline packets](bench/reflection-baseline.ar1)
- A separate **15-frame live GUI run** received checksum-valid data with zero reported dropped FPGA frames. MIC2 was zero in every frame and five channels were active. No bearing passed the directional checks during this run. The app retained 36 mm column spacing, 55 mm row spacing, and unmeasured/approximate status. [Live observations](bench/reflection-live-check.json), [live GUI capture](bench/reflection-live.png)
- Accepted-source, suppressed-source and raw-overlay views were rendered in both themes. Synthetic examples and recorded replays are explicitly labeled. [Synthetic source, dark theme](bench/reflection-dark-source.png), [baseline replay, light theme](bench/reflection-light-suppressed.png)

The synthetic direct-plus-echo case uses six independently delayed waveforms, a 6.25 ms reflection delay and reflection amplitude 0.55 relative to the direct wave. The reported direct direction was within the test's 6° tolerance. Equal-amplitude direct and reflected waveforms were rejected as ambiguous. These are deterministic regression examples, not a room-performance specification. A coherent persistent reflection is explicitly tested as a case that can still pass the filter. Known physical source positions and measured sound-port spacing are required for a real reflection-rejection accuracy assessment; that assessment has not been performed.

## Gentle filtering adjustment — 2026-11-16

After the user reported that humming disappeared with the filter enabled, the previous behavior was retained as **Strong**, and **Gentle** became the dashboard default and saved choice. Gentle permits broad responses, centers flat maxima caused by correlation quantization, and keeps an existing direction only while current microphone evidence still supports a nearby peak. Marginally stronger opposite peaks do not immediately steal that track. Broad/competing results are marked approximate. The volume-decay gate is disabled in Gentle mode.

- **28 Python/Qt tests passed**, including all previous Strong-mode regression cases. New tests reproduce Strong-mode rejection of quantized 100, 150, 200, 300 and 500 Hz tone profiles, verify Gentle-mode visibility and plateau centering at five angles, cover MIC2 silence, check persistence with a marginally stronger opposite lobe, require confirmation of a clear opposite move, and ensure silence and completely flat evidence remain rejected. The tone profiles use the analytical pair correlation of a stationary sinusoid; they are simulations, not recordings of the user's hum. [Test log](bench/gentle-tests.log)
- Replaying the previous 40-frame live baseline in Gentle mode accepted zero weak-signal bearings. [Replay result](bench/gentle-baseline-check.json)
- Both themes were visually checked with a labeled 150 Hz synthetic example showing a broad approximate direction. [Dark](bench/gentle-dark-hum.png), [light](bench/gentle-light-hum.png)
- A 10-frame live GUI smoke check passed with zero reported dropped FPGA frames, Gentle selected, and the 36/55 mm estimated spacing preserved. MIC2 remained zero; no candidate passed during this unlabelled ambient capture. This checks live integration, not humming accuracy. [Live observations](bench/gentle-live-check.json), [screenshot](bench/gentle-live.png)

Actual humming from a known location is still needed to judge this adjustment in the room. Continuity can preserve an incorrect initial direction if that direction remains supported; it is not proof of direct-path sound. The smaller correlation thresholds deliberately trade some rejection for visibility.

## Phone to the right: channel mapping check

The user reported music playing beside MIC3 and MIC6, corresponding to approximately 90 degrees. Sixty live packets were captured in [phone-right.ar1](bench/phone-right.ar1). Gentle accepted only three instantaneous candidates and its tracker displayed none; 43 frames failed pair agreement. Unfiltered correlation already often favored the wrong side, so filtering alone was not the full problem.

Pair-delay inspection suggested lower-left/middle channels 4 and 5 may be reversed. Replaying the same data with only those two physical positions exchanged substantially improved the result: over 27 louder windows (median nonzero energy greater than 20,000,000), median angular error from the reported right side changed from 109 degrees to zero. Unfiltered valid candidates changed from 19 to 22. This is a diagnostic hypothesis from one source placement, not independent physical wire verification. [Comparison](bench/phone-right-mapping-comparison.json)

The user chose to rewire to the normal documented layout. An updated two-page [rewiring PDF](../wiring/six_microphone_rewiring_guide.pdf) shows microphone positions followed by the verified JE connector drawing. Filtering is saved off and the software swap is saved off. The physical rewire and subsequent known-source check have not yet happened. A software mapping option is available for future diagnosis, and 30 Python/Qt tests passed, including channel permutations with lag-axis reversal and different source directions. [Tests](bench/channel-mapping-tests.log)

## After the physical rewire — 2026-11-16

The user confirmed rewiring according to the PDF. The initial 60-frame capture contained weak ambient sound; the user then confirmed the music had been off and restarted it to the right of MIC3/MIC6. That initial capture is not used to assess direction. The board remained on the radar profile and the internal self-test passed all 15 pairs. [Board status](bench/after-rewire-board.log), [self-test](bench/after-rewire-self-test.log)

The subsequent **80-frame phone-right capture** reported zero dropped FPGA frames. Across all 80 windows, 48 passed the existing unfiltered bearing checks; their bearings ranged from 83 to 98 degrees, with a median of 90 degrees. Using the normal documented channel order, the 23 louder windows had a median angular error of 1 degree relative to the user's approximate 90-degree placement. Of those, 21 passed the bearing checks; all 21 were within 20 degrees of right. This is one practical source-placement check using estimated geometry, not a calibrated angular-accuracy specification.

The cross-channel timing now agrees with the normal layout: MIC1/MIC4 and MIC3/MIC6 had zero-sample correlation peaks, MIC4/MIC5 peaked at -5 samples (predicted -5.04), and MIC1/MIC3 peaked at -9 samples (predicted -10.08). Replaying with MIC4/MIC5 exchanged now worsens the louder-window median error to 147 degrees. Keep **Swap MIC4 / MIC5 positions unchecked**. Reflection rejection remains off as requested.

MIC2 reported exactly zero energy in all 80 windows. The five other channels were active. The remaining MIC2 fault could be in its module, wiring, or input path; the internal self-test does not exercise those external parts. [Capture and analysis](bench/after-rewire-phone-right-analysis.json), [CRC-protected packets](bench/after-rewire-phone-right.ar1), [labeled replay image](bench/after-rewire-verified.png)

## GUI level gate — 2026-11-16

Added the requested horizontal level slider directly above the degree chart, with an enable checkbox, threshold label and live array-level readout. It spans -60 to 0 relative dB and starts at -22 dB. Below the threshold it hides both the main directional response and raw overlay while preserving live channel meters. Array level is the median active-channel power, excluding silent MIC2. Threshold and enable state persist, and slider movement redraws the current frame immediately. Reflection rejection was switched off again after the user clarified that it was hiding too much.

- **36 Python/Qt tests passed**, including above/below/exact-threshold behavior, raw-overlay hiding, live meters, keyboard slider adjustment, disabled-gate bypass, silent-channel handling, tracking reset, settings persistence and malformed-setting recovery. [Test log](bench/level-gate-tests.log)
- Both themes were visually checked at the user's window size. Replaying an actual quiet capture at about -24 dB closed the gate; a music window at -18.7 dB displayed approximately 90 degrees. [Open gate](bench/level-gate-dark-open.png), [closed gate](bench/level-gate-light-closed.png)
- A 12-frame live UART check exercised both ends of the slider against incoming microphone data, verified immediate chart hiding and restoration, and confirmed that channel meters remained active. No dropped FPGA frames were reported. [Live check](bench/level-gate-live-check.json), [live screenshot](bench/level-gate-live.png)

This is a gate on overall frame level, not separate per-direction intensity measurement or echo cancellation. The dB scale is relative to the FPGA's scaled samples and is not calibrated SPL.
