# One riff around the array

Film the guitar and array from directly above. Put the overhead footage on the left and the live radar on the right. For the final shot, overlay the measured bearing on the camera image. The audience can judge each chord by watching where the ray points relative to the guitar.

## The take

| Time | Performance | What the audience can check |
| --- | --- | --- |
| 0–5 s | Stand on the M3 side and play two short, separated chords. | The sound hole is to the right of the array. Look for a bearing near 0°. |
| 5–15 s | Walk a slow arc while repeating the riff. Reverse halfway through a phrase. | The audience sees the bearing change direction with you. |
| 15–22 s | Mute the strings, step quietly to the opposite side and hold still for a beat. Strike one chord. | Watch for the gate to clear the ray in the gap and for a fresh bearing on the next attack. |
| 22–30 s | Finish with a few spaced strums. Switch to the overlay from the same take. | Each visible bearing starts at the real array center and points across the same camera frame as the instrument. |

## Set up the two views

- For new hexagon takes, orient the harness at the upper right. Mark the array center and the new M3 (JE10) direction with tape. Frame the phone overhead with M3 pointing to screen-right and the M1/M2 edge at the top. Strum once on that side to check rotation and mirroring.
- Use the acoustic guitar itself as the sound source. If playing through an amp, the speaker becomes a second possible source. Record the guitar audio for the edit.
- Press **Record take** on the live Wi-Fi or Ethernet dashboard, wait for the recording timer, and start the phone camera. Make one visible clap near the array, wait a beat, then play. A second clap at the end lets you check for drift on a long phone clip.
- Before filming, compare the live level in a quiet pause, while walking, and during a soft strum. Set the existing gate where the quiet interval clears and the soft strum still registers. Use deliberate chords with space between attacks at roughly twelve radar updates per second.

## Replay and cut the video

1. Click **Stop recording**. **Replay last take** opens the most recent recording. After restarting the app, click **Replay take…** and select the take's `take.jsonl` in `~/Videos/Acoustic Radar/`.
2. Under **Audio**, choose **M1 only** or **All six mics**. The second choice averages M1–M6 at equal levels into one mono track. You can switch at the current playhead and the app remembers your choice. Click **Play** or drag the timeline to a strum. A gated or silent interval plays its original sound while the bearing clears. Replay works with the Zybo switched off.
3. Choose **Export MP4…** for a square 1080 × 1080, 30 fps H.264 clip with the selected soundtrack. Export uses the stored measurements and the FPGA sample clock. It works independently of your screen size and playback speed.
4. New recordings show the PC's local start time and 30 fps timecode in Replay. Each WAV carries the first sample's local time as a Broadcast Wave time reference. The exported MP4 carries that same local timecode and a UTC creation timestamp at whole-second resolution. The WAV time reference and take log retain subsecond timing. In a timecode-aware editor, use these to place the radar and audio on the timeline.
5. Place the phone footage and the radar clip side by side in your editor. Match the first clap on the two audio waveforms. Keep one audio track audible to avoid doubling. Phone and PC clocks run independently. Use their times for a rough match and the clap waveform for the exact alignment. For a longer take, check the closing clap too.

The PC brackets the first FPGA audio sample between releasing the armed recorder and receiving its first 512-sample packet. It saves the bracket midpoint in UTC and local time, plus the bracket half-width in milliseconds, in the `clock` field at the end of `take.jsonl`. This interval describes network and start-up timing against the PC clock. The FPGA counter gives each recorded radar window its audio-relative time at 48,000 samples per second. Older takes retain their sample timing and can use the six-mic mix when `microphones.wav` is present. An older take's folder name records when the folder was created. [Broadcast Wave format specification](https://tech.ebu.ch/docs/tech/tech3285.pdf)

Each timestamped folder contains:

| File | Content |
| --- | --- |
| `microphones.wav` | Six synchronous signed 24-bit, 48 kHz channels in the take’s M1–M6 order. New takes list their one-based FPGA inputs in the take footer under `fpga_channels`. |
| `guitar.wav` | The recorded M1 waveform (JE8 for the current hexagon) in an editor-friendly mono WAV. Any other mic can be extracted from the six-channel master. |
| `take.jsonl` | Sample-indexed radar windows, six energies, 15 correlation profiles, geometry, displayed bearings, approximate flags, curves, gates and transient markers. |
| `radar.mp4` | Created when you export. Its soundtrack comes from the same take. |

The live gate controls the visualization. All six waveforms continue through quiet passages. Saving both WAVs takes about 60 MB per minute, plus radar data. The recorder checks packet continuity and reports an interruption if the network or FPGA stops. A finalized partial take retains its contiguous audio. Ordinary RIFF WAV limits a single take to roughly 82 minutes.

Replay and export use each take’s recorded orientation. Earlier recordings match footage taken with the earlier camera orientation.

The main chart keeps its title and degree readout in fixed positions. Amber marks indicate recent attacks with a directional estimate. **Show diagnostics** reveals the five-second bearing history, gate status and window details. **F11** opens a clean full-screen view.
