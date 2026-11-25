# Acoustic Radar demo

[Watch the 1:10 film](acoustic-radar-demo.mp4)

Ryan’s filmed guitar trial, spoken introduction and board walkthrough come from the original [Acoustic Radar Demo.mp4](https://rlongwell.github.io/fpga-acoustic-radar-public/). The 339° figure is the net change in estimated bearing over 69 logged detections. It describes this take and does not measure absolute angular error. The new overlay animates all 15 microphone pairs.

## On-screen script

| Time | Scene | Overlay |
| --- | --- | --- |
| 0:00 | Acoustic Radar | Finding a guitar by sound. A live guitar moves around the array. Can six microphones follow its bearing? |
| 0:05 | The guitar trial | Watch the source move around the stationary array. Live recording |
| 0:11 | Array geometry | Six channels. 15 microphone pairs. The FPGA correlates every pair at 65 time lags. The desktop fits a horizontal bearing to those delays. |
| 0:18 | Reading the compass | The lobe points toward the estimated sound source. Horizontal bearing |
| 0:26 | Around the table | The trace records the change in estimated bearing. 69 detections |
| 0:34 | Microphone array | Shared clocks keep all six microphone channels in step. 48 kHz |
| 0:42 | Inside the enclosure | The microphone signals enter the Zybo through the JE header. I²S |
| 0:50 | Signal processing | Programmable logic builds a delay profile for each pair. 4,096 frames / window |
| 1:01 | Capture and replay | A sample counter aligns the recorded audio and bearing trace. Six-channel PCM |

## Evidence and reproduction

- [radar.md](../../radar.md)
- [hexagon.md](../../hexagon.md)
- [guitar_demo.md](../../guitar_demo.md)

[Verification](verification.json) records the exported file hash, frame count, full decode and source-audio alignment. The source picture and sound are from the recorded project. Titles, overlays and editing were AI-assisted.
