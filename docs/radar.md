# Acoustic radar operator and development guide

The FPGA captures six synchronized microphone channels and computes the 15 pairwise correlations. The Zybo Linux bridge streams those correlations over wired Ethernet by default. Wi-Fi and USB UART are also available. The desktop applies the array geometry to estimate the horizontal bearing of one dominant sound. Gentle filtering is enabled by default: the green plot shows an accepted source lobe, with uncertain directions marked approximate. The polar radius represents relative directional evidence, not distance.

## Run the dashboard

1. Connect the six-microphone hexagon with a separate SD lead per microphone. In dashboard order, M1 through M6 connect to JE8, JE9, JE10, JE7, JE4 and JE3. The XDC uses FPGA channel numbers. [Hexagon positions, connector and calibration](hexagon.md)
2. With the [standalone starter card](starter-card.md), connect USB and run `./dashboard.sh --port auto`. With the network-enabled bench image, open `./dashboard.sh` and power up the Zybo in either order. The default **Ethernet · wired SSH** mode connects to the saved host **zybo-wired** and starts the stream when Linux is ready. Leave the window open when switching the board off and on. The display clears stale readings and reconnects automatically. **Disconnect** pauses retries and releases the active stream. **Connect** resumes automatic connection. **Demo** switches to simulated data.
3. In **Hexagon** mode M1 is upper left and the microphones are numbered clockwise as viewed from the component side with the harness at upper right. Their data pins in GUI order are JE8, JE9, JE10, JE7, JE4 and JE3. Bearings increase counterclockwise from 0° at M3 (right). The bottom edge between M4 and M5 is 270°. Enter actual port offsets under **Acoustic-port coordinates…** and set the air temperature. Until measured, live bearings use the intended mounting coordinates and display as approximate.
4. For the older two-row breadboard, select **2 × 3**. This mode uses the saved rectangular spacings and the original clockwise-from-front convention. `./dashboard.sh --demo` supplies simulated input for the selected geometry.

## Wired connection

On this bench the PC uses `10.77.78.1` and the Zybo uses `10.77.78.2` on `eth0`. The host alias `zybo-wired` supplies the board address, account, SSH key and pinned host key. The dashboard runs OpenSSH in batch mode and checks that the session reached an address assigned to the board’s Ethernet interface. Watch for **Ethernet** on the live frame counter. A lost link clears stale bearings and retries the same transport.

To select another wired SSH host, use `./dashboard.sh --host HOST`. For the USB console, select **Disconnect**, choose **USB UART**, then select **Connect**, or pass `--port /dev/serial/by-id/…`. A fresh GUI settings file defaults to Ethernet. Connecting saves the selected transport and its host for the next launch.

## Wi-Fi connection

On this PC, `ssh zybo-wifi` connects to the board’s wireless address with its pinned SSH host key. Open `./dashboard.sh --wifi`, or select **Disconnect**, **Wi-Fi · wireless SSH**, then **Connect**. The host field defaults to `zybo-wifi`. Use `--wifi HOST` to override it. If DHCP changes the board’s address, update the wireless SSH alias or use the matching SSH configuration for the new address.

The header identifies the PC interface and the Zybo interface when both can be established from the SSH socket. On the demo PC, **PC Ethernet → Zybo Wi-Fi** uses the NetworkManager profile `Zybo radar wired LAN`. Its DHCP interface `radar-lan` runs on the physical `enp3s0` Ethernet port. A host route selects the wireless Zybo at `192.168.1.21`. A profile-specific NetworkManager dispatcher restores the verified Panda neighbor entry when the link comes back. The direct RDP addresses coexist on the parent interface. The route is specific to the board. If the board DHCP address changes, update the route, neighbor entry and SSH alias together. The menu's Wi-Fi choice specifies the board end of the connection. Before starting the radar bridge, the dashboard verifies that the board received the SSH connection at its `wlan0` address and routes replies to the PC over that interface. It keeps retrying Wi-Fi after a disconnect. The FPGA and board-side bridge use the same capture format and cadence as wired SSH.

## Reflection rejection

For the current wiring check, **Reject reflections is off** and the original instantaneous response is visible. After confirming the wiring, Gentle and Strong remain optional. Choose **Strong** when you prefer rejecting broad or ambiguous responses. These settings are saved in `.settings/gui.json`. The optional raw response is a gray diagnostic overlay containing noise, sidelobes and possible reflections. Its bumps do not identify additional objects or sources.

For the older **2 × 3** mode, the top row reads MIC1–2–3 (JE7, JE4, JE3) and the bottom row reads MIC4–5–6 (JE8, JE9, JE10). The FPGA assigns the channels before computing energies and pair correlations, so the dashboard meters and bearing plot use the same microphone numbers. Leave **Swap MIC4 / MIC5 positions** unchecked with this harness. Sound beside MIC3 and MIC6 is at 90 degrees. [Position-first wiring guide](../wiring/six_microphone_rewiring_guide.pdf)

### Adjustable level gate

The **Level gate** slider sits directly above the degree chart. It starts enabled at **-22 dB**, can be adjusted from -60 to 0 dB in 1 dB steps, and saves its value and enabled state in `.settings/gui.json`. Move it **right** to require louder sound; move it **left** to show quieter sound. Uncheck **Level gate** to bypass it. Arrow keys change the selected slider by 1 dB; Page Up/Down change it by 5 dB.

The **Array** readout uses the median power of active microphones on the same relative scale as the channel meters. Quiet microphones are excluded. These values are not calibrated dB SPL. Below the threshold, the entire directional response, bearing marker and optional raw overlay are hidden; the six microphone meters keep updating. The chart reappears at or above the threshold, subject to the existing direction checks. Dragging the slider updates the current frame immediately. No extra hold time or hysteresis is applied.

The gate uses overall array level; it does not measure each direction's separate sound intensity or selectively remove an echo while louder sound is present. Reflection rejection remains a separate option and is currently off at the user's request. If reflection rejection is enabled later, closing the level gate clears its tracking history so hidden samples do not confirm a future bearing.

In replay checks, the captured quiet background was about -24 dB and was hidden at the -22 dB starting threshold; an example music window at -18.7 dB remained visible around 90 degrees. Adjust the slider for the current room and playback volume rather than treating -22 dB as a universal calibration.

### Gentle mode for humming and steady sound

The initial Strong filter required narrow, high-contrast correlation peaks. Regression tests with 100–500 Hz tones at the current array dimensions reproduced its rejection of humming-like signals. Gentle mode uses the original mean correlation curve, a 0.10 correlation floor, agreement from at least half of active pairs, and at least 0.006 angular variation. A pair supports a candidate when its interpolated correlation is at least 0.08 and the nearest sampled lag is within 0.04 of its maximum over physically possible delays. It permits broad peaks and does not suppress a source merely because its volume decreases.

The limited 8-bit correlation precision can create a flat angular maximum. Gentle mode uses the center of a connected flat maximum instead of selecting its first angle. It labels a response approximate when its lead over directions at least 75° away is less than 0.025. The dashed ray and `≈` also remain in use while the geometry is unmeasured. A completely flat response still gives **Sound detected; direction unresolved**.

Once a direction has been acquired, Gentle mode checks for a currently supported peak within 25° of it. That peak is retained if it remains within the larger of 0.012 correlation or 15% of the full angular score range of the global maximum, and still passes the absolute correlation and pair-agreement gates. This prevents marginally stronger opposite lobes from immediately stealing the marker. Such a result is explicitly approximate. The plotted lobe follows this selected peak. A clearly stronger opposite direction needs four frames (about 0.6 s after the first candidate); ordinary direction changes need three. A new source usually needs two frames, with the existing clean-onset exception. Silence and stale data still clear the display.

Gentle mode trades strict rejection for visibility and continuity. It does not establish which of two plausible directions is correct, and may retain the wrong initial direction while it remains supported. Low-frequency resolution is limited by small array aperture; this is a broader microphone-array limitation ([low-frequency localization study](https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2023.1172536/full)). An opposite-side reading alone does not prove an echo. Try a steady hum first, then speech from the same location to compare the response. Actual humming in this room still needs user validation.

### Strong mode

Strong mode applies these checks to each frame:

1. Evaluate only geometrically possible pair delays, remove the median correlation baseline for each pair, and normalize its peak contrast. Trim the strongest fifth of pair contributions so a few strong pairs cannot determine the direction alone. Quiet microphones remain excluded.
2. Require mean normalized correlation of at least 0.12 and at least 65% of available pairs near their individual peaks. A supporting pair needs at least 0.08 contrast, 0.08 correlation and 60% of its peak contrast at the predicted delay.
3. Reject broad or competing directions: the leading robust score must beat every angle at least 30° away by at least 0.06 and 12% of its peak value. These thresholds are conservative engineering defaults, not calibrated probabilities.
4. Confirm a new source over two received frames and a jump more than 25° from the tracked source over three. At the wired update rate, this adds about 85 ms and 171 ms after the first candidate frame. The USB UART equivalents are about 200 ms and 400 ms. Nearby bearings use circular smoothing, including across 359°/0°. Repainting the same frame never counts as new evidence. A very clear onset with a fourfold power rise can appear immediately when no source is tracked, so some short claps remain visible.
5. Suppress falling sound power below 18% of a recent accepted peak. The reference decays with a 0.8 s time constant so a quieter sustained source can be acquired again. This is an echo-tail heuristic and may also hide a real fading source. Tracking history expires after 0.65 s without acceptance, and data gaps over 0.8 s reset confirmation.
6. Display only the connected lobe around an accepted maximum, above 55% of its peak-to-mean contrast. Clear the bearing immediately for ambiguity and clear the entire live result when telemetry is more than one second old. **No clear source** is an intentional result, not a frozen display.

Both modes perform source selection and display filtering. They do not subtract echoes from microphone audio, and cannot prove a wavefront came directly from the source. A strong, stable reflection can satisfy all checks. Two real speakers can also produce competing directions. The design assumes one dominant, approximately horizontal far-field source; a close or elevated source and inaccurate array dimensions can reduce agreement. One silent microphone reduces the usable pairs from 15 to 10.

The existing FPGA integrates 4096 samples (85.3 ms) per window. The bridge sends up to 11.7 quantized correlation profiles per second over Ethernet or five over USB UART. Direct sound and early room reflections can already be mixed in one window; their arrival order cannot be recovered from this telemetry. Published direct-path methods select suitable time-frequency bins, sometimes using onset information ([Wang and Lu](https://arxiv.org/abs/1904.06648), [Rafaely and Alhaiany](https://arxiv.org/abs/2310.03688)). PHAT uses frequency-domain weighting ([Zhang, Florencio and Zhang](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/WhyPHAT.pdf)). None of those algorithms is claimed here. A further DSP upgrade would need short-time multichannel samples or spectral statistics from the FPGA/ARM path, followed by room tests with known source locations.

For a practical check, keep the array fixed, speak from one marked direction for several seconds, pause, and repeat from another direction. The source marker should settle during clear sound and disappear when evidence is weak. Compare briefly with the gray raw overlay to see what is being suppressed. Short claps may be hidden if they do not pass the onset check. This controlled check, plus actual sound-port spacing measurements, is still needed to judge performance in your room.

## Build, deploy, and select the boot profile

For a fresh board, follow the [standalone USB and microSD instructions](starter-card.md). The following deployment commands are for the original shared Linux installation. From the project root, run `./scripts/test.sh`, `./build.sh`, and `./deploy.sh`. The test uses Python and Verilator. The FPGA build uses AMD Vivado 2024.2 and the included Digilent board preset. Set `VIVADO` or `ZYBO_BOARD_REPO` to override their locations. The board software build uses the shared Buildroot ARM compiler, the shared SD rescue DTB, DTC, and U-Boot mkimage. See the defaults and environment overrides in [build_board_software.sh](../scripts/build_board_software.sh).

Deployment creates a verified package in `build/`, transfers it through the existing Zybo uploader, installs the profile, reboots into it, and verifies the internal FPGA self-test. The hardware and device tree are in `/boot/profiles/radar/`. The Linux bridge is `/opt/zybo/radar/radar-stream`. The build artifacts include `build/system.bit`, `build/bitstream.SHA256`, and `build/reports/{io,timing,utilization,drc,route}.rpt`. On the configured SD card, U-Boot reads `/boot/profile.env` and loads the radar bitstream and DTB at power-up. Linux exposes the UIO device, and connecting the dashboard starts the selected stream. To choose another default from the Zybo console, run `zybo-profile select hash` (or another installed profile). To restore radar as the default, run `zybo-profile select radar`. A selection takes effect at the next boot. The PC command `python3 scripts/board.py boot` remains available for a one-time radar session when another profile is selected.

Use `python3 scripts/board.py check` to verify the active Linux profile and build ID, `python3 scripts/board.py self-test` for the 15 known correlation peaks, and `python3 scripts/board.py capture` for one real UART frame and its six channel energies. Each command needs the UART free. Disconnect live capture before running the self-test or starting a separate capture. The run status and remaining physical checks are recorded in [radar_validation.md](../verification/radar_validation.md).

## RTL and UART interface

The FCLK0 is 100 MHz. The fractional I²S generator alternates 160 and 170 ns clock half-periods. Average SCK is 3.072 MHz and WS is 48 kHz. Six inputs capture 24 bits in parallel, one bit after the I²S left slot starts. The receiver drops the first 4096 frames for microphone startup and fills a 32-frame delay history. It differences consecutive signed samples, shifts right by five, and clips to signed ten bits. One 4096-frame window produces 65 signed lag bins per pair and six energy sums. Lag greater than zero means that the wave reached the higher-numbered mic later. Pairs are ordered (1,2), (1,3), …, (5,6), with each pair's bins in ascending lag order. Internal test mode drives the pins low and feeds the correlator the same internal sequence with six known delays.

The recording profile DTB binds a 256 KiB UIO range at `0x43c00000`. The board program verifies the register magic and ABI before streaming.

| Offset | Register |
| --- | --- |
| `0x0000` | Magic `0x41524452` |
| `0x0004` | ABI `0x00010000` |
| `0x0008` | Mode 0 idle, 1 live, 3 self-test |
| `0x000c` | Completed-window sequence number |
| `0x0010`, `0x0014` | Incoming frame and dropped frame counters |
| `0x0020`–`0x0034` | Six unsigned energy sums |
| `0x0038` | Recording capability, `0x50434d36` (PCM6) |
| `0x003c` | FPGA sample count at publication of the completed correlation window |
| `0x1000`–`0x1f38` | 975 signed 32-bit correlation bins |
| `0x10000`–`0x3ffff` | Six 8192-frame read-only PCM banks, 0x8000 bytes per mic, one 24-bit sample per aligned word |

The board's `--pcm` bridge observes an existing live session. It reads the six banks in 512-frame blocks and verifies the hardware write pointer before and after each copy. Each network packet starts with little-endian `<4sIII` fields for PCM6 magic, first sample counter, frame count, and sample rate, followed by interleaved signed packed 24-bit little-endian PCM. The dashboard saves the audio continuously and timestamps each radar window against that sample counter. A 4096-frame radar window covers about 85 ms. Network jitter does not change the audio time used for replay. The capture and editing workflow is in the [guitar demo guide](guitar_demo.md).

The UART is 115200 8N1. A line begins with `AR1`, followed by source `L` (live) or `T` (FPGA test), decimal sequence, frame count, dropped-frame count, six comma-separated decimal energies, 1300 Base64 characters, and an eight-digit hex CRC32 of everything before the space preceding the CRC. The payload decodes to 975 signed 8-bit bins, scaled by the geometric mean of each pair's channel energies. USB UART updates are limited to five per second. Ethernet sends the same CRC-checked packet for each new 4096-sample window over SSH. The GUI starts the foreground bridge and sends a heartbeat about every two seconds while valid live frames are arriving. Ctrl+C or an eight-second heartbeat timeout stops capture and returns the console. The bridge resumes capture when the GUI reconnects. The six displayed levels are relative to the FPGA's scaled signal, in dB, without SPL calibration.

The FPGA computes the lag profiles entirely in programmable logic. The desktop evaluates predicted arrival differences for each degree using the rectangular geometry and linearly interpolates the FPGA bins. The reported angle depends on the geometry, sound speed approximation, and the clarity of the received signal.
