# Six-microphone hexagon on Pmod JE

View the microphone side with the wire harness at the **upper right**, a half turn from the original wiring photo. **M1 is upper left. Follow the microphones clockwise to M6 on the left.** The chart measures bearings counterclockwise from the right. Straight down between M4 and M5 is 270°.

```text
                       90°
                 M1           M2

        180°  M6        +        M3  0°

                 M5           M4
                      270°
```

| GUI mic | Position | Board column | Board row / label | View X (mm) | View Y (mm) | SD to JE | FPGA pin | FPGA channel |
| --- | --- | ---: | --- | ---: | ---: | --- | --- | ---: |
| M1 | Upper left | 46 | 44 / R, second | −22.86 | +38.10 | JE8 | U17 | 4 |
| M2 | Upper right | 28 | 44 / R, second | +22.86 | +38.10 | JE9 | T17 | 5 |
| M3 | Right | 19 | 29 / C, second | +45.72 | 0.00 | JE10 | Y17 | 6 |
| M4 | Lower right | 28 | 14 / N, first | +22.86 | −38.10 | JE7 | V13 | 1 |
| M5 | Lower left | 46 | 14 / N, first | −22.86 | −38.10 | JE4 | H15 | 2 |
| M6 | Left | 55 | 29 / C, second | −45.72 | 0.00 | JE3 | J15 | 3 |

The 74-column × 57-row board has its nominal array center at column 37, row 29. The table uses the intended acoustic openings and an assumed 2.54 mm pitch. Adjacent baselines are 44.43 or 45.72 mm. The opposite pairs are M3–M6 (91.44 mm) and M1–M4 and M2–M5 (88.86 mm each). M1–M5 and M2–M4 each span 76.20 mm vertically. The solver uses these X/Y coordinates directly.

All six SCK pads go to JE1, all WS pads to JE2, VDD to the JE6 3.3 V rail, and all GND and L/R pads to the JE5 ground rail. Each SD is private. Looking into the female JE socket with the board below it, pin 1 is upper right and pin 7 is directly below it. The hexagon wiring diagram uses the dashboard’s M1–M6 labels. [JE plug-in diagram](../wiring/six_microphone_hexagon_plug_in_guide.pdf)

## Run and calibrate

1. Open `./dashboard.sh` and select **Hexagon · 0° right, CCW**. The configured SD card boots radar automatically. Leave the dashboard open when restarting the board. It reconnects after Linux starts. The deployed FPGA acquires all six channels synchronously and sends energies and 15 pair-correlation profiles.
2. Use **Acoustic-port coordinates…** to enter measured X/Y offsets in millimeters relative to the center, with +Y toward the top. Mark the checkbox after measuring the openings. The starting values above are mounting targets. Geometry edits affect both live and demo steering.
3. Set **Air temperature** to the air temperature near the array. The model uses 343 m/s at 20 °C, scaled by the square root of the absolute-temperature ratio. It updates both steering delays and the physically allowed lag for each pair. [NASA Glenn speed-of-sound relation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/speed-of-sound-interactive/)
4. Place a speaker about a metre from the array center at microphone height. Use broadband speech or music on the M3 side and then centered below M4/M5. Expected bearings are around 0° and 270°. The plotted radius shows directional evidence. Three active, non-collinear channels are the minimum for a unique horizontal direction. Check the six meters if the chart is empty.

## Checking a silent channel

Switch off and unplug the Zybo before moving leads or measuring continuity. Trace the silent microphone's **printed SD pad**, through its solder joint and harness, to the JE socket in the table. Also check that its VDD, GND, SCK, WS and grounded L/R reach the module. Partially connected protoboard rails can leave a group of microphones without one of the shared connections.

To isolate GUI M5, temporarily exchange only its SD lead at JE4 with the working GUI M3 SD lead at JE10, then power up and run the radar again. If activity moves to meter M5 and M3 goes quiet, JE4 can read the working module and the fault follows the original M5 module or harness. If M3 responds to the previously silent M5 and M5 stays quiet with the known-good lead, investigate the JE4 contact/input path. Power down and restore both leads before checking direction.
