# Rectangular 2 × 3 breadboard on Pmod JE

For the current protoboard, use the [hexagon position and wiring table](hexagon.md).

A single solderless breadboard can distribute the signals from JE to six microphones. JE has exactly eight GPIOs for two shared clocks and six independent SD inputs. The six-microphone configuration uses its own XDC. Select that file as the JE constraints for a design with six SD input ports. [Six-microphone XDC](../constraints/zybo_z7_20_je_inmp441_6mic.xdc)

With the array's marked edge nearest you, MIC1 is upper left and feeds JE7. MIC3 is upper right and feeds JE3. Face the female JE socket with the Zybo PCB below it. Pin 1 is upper right, pin 7 is directly below it, and pin 3 is third from the right on the upper row. [Six-microphone connector drawing](../wiring/six_microphone_plug_in_guide.pdf)

| JE socket | FPGA pin | Signal | Breadboard destination |
| --- | --- | --- | --- |
| 1 | V12 | `i2s_sck` | Shared SCK bus to all six microphones |
| 2 | W16 | `i2s_ws` | Shared WS bus to all six microphones |
| 3 | J15 | `mic3_sd` | Private strip to MIC3 SD (upper right) |
| 4 | H15 | `mic2_sd` | Private strip to MIC2 SD |
| 5, 11 | — | GND | Common ground for all GND and L/R pads |
| 6, 12 | — | 3.3 V | Common supply for all six VDD pads |
| 7 | V13 | `mic1_sd` | Private strip to MIC1 SD (upper left) |
| 8 | U17 | `mic4_sd` | Private strip to MIC4 SD |
| 9 | T17 | `mic5_sd` | Private strip to MIC5 SD |
| 10 | Y17 | `mic6_sd` | Private strip to MIC6 SD |

1. With power disconnected, set up independent 3.3 V, GND, SCK, and WS buses plus six separate SD strips. Each clock bus needs a feed from JE and six microphone connections. If your breadboard has five-hole strips, link two strips to make each clock bus, or allocate an isolated long rail to each clock. Meter the actual rail connections, including any split.
2. Confirm the breakout labels before wiring. Tie each L/R to GND, connect each SD to its private strip, and fit one 100 kΩ pull-down per SD plus one local 100 nF bypass per module where the corresponding component is unconfirmed onboard. [INMP441 datasheet](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf)
3. Meter supply polarity and check for shorts between the SD strips before plugging the harness into JE. Bring up one microphone and add the rest with power off. Keep the clock branches short and run ground alongside them. With all six attached, scope the farthest microphone to check 3.072 MHz SCK, 48 kHz WS and clean clock edges. JE already has 200 Ω series resistors, and signal integrity with six loads has to be checked on the actual harness. [Digilent board reference manual](https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf)

You can keep the breadboard as the wiring hub and mount the microphone modules separately. For horizontal direction finding, spread them across two dimensions, keep the sound ports clear, and record the position of each port against its MIC number.

The FPGA pin assignments follow the official [Zybo Z7 master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc).
