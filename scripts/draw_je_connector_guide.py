"""Render the six-microphone connector page using the active six-channel pin map."""
import re
from pathlib import Path
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def six_channel_je_ports(root):
    xdc = (root / "constraints/zybo_z7_20_je_inmp441_6mic.xdc").read_text()
    return {port: int(pin) for port, pin in re.findall(r"get_ports \{(\w+)\}\].*?# JE pin (\d+)", xdc)}


def draw_connector_guide(pdf_path, ports, *, hexagon=()):
    fontdir = Path("/usr/share/fonts/truetype/dejavu")
    for name, filename in [("Guide", "DejaVuSans.ttf"), ("GuideBold", "DejaVuSans-Bold.ttf"),
                           ("GuideMono", "DejaVuSansMono-Bold.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(fontdir / filename)))

    width, height = letter
    pdf = canvas.Canvas(str(pdf_path), pagesize=letter, pageCompression=1)
    pdf.setTitle("Hexagon microphone wiring | Zybo Z7-20 Pmod JE" if hexagon else
                 "Six INMP441 microphones | Zybo Z7-20 plug-in guide")
    pdf.setAuthor("Acoustic radar project")
    ink = HexColor("#14293A")
    muted = HexColor("#42596D")
    border = HexColor("#D5E1E8")
    soft = HexColor("#F0F5F8")
    teal = HexColor("#00675E")
    red = HexColor("#B52238")
    amber = HexColor("#784002")
    clock_blue = HexColor("#165AC4")
    clock_green = HexColor("#146C43")
    sd_colors = [HexColor(color) for color in ("#D9A300", "#D97523", "#8739B4", "#058682", "#466B91", "#A65C61")]
    sd_pins = [ports[f"mic{i}_sd"] for i in range(1, 7)]
    if hexagon:
        from radar.protocol import HEX_INPUTS
        sd_pins = [sd_pins[channel] for channel in HEX_INPUTS]

    def box(x, y, w, h, fill, stroke=None, radius=0):
        pdf.setFillColor(fill)
        if stroke is not None:
            pdf.setStrokeColor(stroke)
            pdf.setLineWidth(0.8)
        if radius:
            pdf.roundRect(x, height - y - h, w, h, radius, stroke=int(stroke is not None), fill=1)
        else:
            pdf.rect(x, height - y - h, w, h, stroke=int(stroke is not None), fill=1)

    def label(x, y, value, size=11, color=ink, font="Guide", align="left"):
        pdf.setFont(font, size)
        pdf.setFillColor(color)
        draw = {"left": pdf.drawString, "right": pdf.drawRightString, "center": pdf.drawCentredString}
        draw[align](x, height - y, value)

    def rule(x1, y, x2, color=border, weight=0.7):
        pdf.setStrokeColor(color)
        pdf.setLineWidth(weight)
        pdf.line(x1, height - y, x2, height - y)

    def circle(x, y, radius, color):
        pdf.setFillColor(color)
        pdf.circle(x, height - y, radius, stroke=0, fill=1)

    def source(x, baseline, title, url):
        size = 8.5
        label(x, baseline, title, size, teal, "GuideBold")
        length = pdfmetrics.stringWidth(title, "GuideBold", size)
        pdf.linkURL(url, (x, height - baseline - 2, x + length, height - baseline + size), relative=0)
        return x + length

    if hexagon:
        box(0, 0, width, 84, ink)
        label(32, 23, "ACOUSTIC RADAR  /  ZYBO Z7-20", 10, HexColor("#A9E2DA"), "GuideBold")
        label(32, 53, "Plug in six INMP441 mics", 26, white, "GuideBold")
        label(33, 73, "Hexagon protoboard   /   M1 upper left, numbered clockwise", 11, HexColor("#DDEBF1"))
        box(32, 97, 548, 31, HexColor("#FFF5E7"), HexColor("#EDD5A9"), 7)
        label(45, 117, "Switch off and unplug the Zybo before wiring.", 11.5, amber, "GuideBold")
        label(565, 117, "3.3 V ONLY", 10.5, amber, "GuideBold", "right")
    else:
        box(0, 0, width, 113, ink)
        label(32, 32, "ACOUSTIC RADAR  /  ZYBO Z7-20", 11, HexColor("#A9E2DA"), "GuideBold")
        label(32, 70, "Plug in six INMP441 mics", 31, white, "GuideBold")
        label(33, 94, f"Six-channel FPGA build  |  MIC1 at JE{ports['mic1_sd']}, MIC3 at JE{ports['mic3_sd']}", 12, HexColor("#DDEBF1"))

        box(32, 130, 548, 57, HexColor("#FFF5E7"), HexColor("#EDD5A9"), 9)
        label(46, 152, "Switch off and unplug the Zybo before wiring.", 12, amber, "GuideBold")
        label(46, 172, "Keep the 3.3 V bundle and the GND bundle electrically separate.", 11, ink)

    pdf.saveState()
    if hexagon:
        pdf.translate(0, 62)
    label(32, 215, "Find the sockets on Pmod JE", 17, ink, "GuideBold")
    label(32, 235, "Look into the female socket with the circuit board below it. Pin 1 is upper right.", 10.7, muted)

    socket_labels = {
        ports["i2s_sck"]: ("SCK", clock_blue), ports["i2s_ws"]: ("WS", clock_green),
        5: ("GND", ink), 6: ("3.3 V", red),
        11: ("GND spare", muted), 12: ("3.3 V spare", muted),
    }
    for i, (pin, color) in enumerate(zip(sd_pins, sd_colors), start=1):
        socket_labels[pin] = (f"M{i} SD" if hexagon else f"MIC {i} SD", color)
    box(32, 249, 548, 118, HexColor("#273D4D"), radius=10)
    for row, sockets in enumerate(((6, 5, 4, 3, 2, 1), (12, 11, 10, 9, 8, 7))):
        for index, pin in enumerate(sockets):
            x = 44 + 87.3 * index
            y = 260 + 50 * row
            name, signal_color = socket_labels[pin]
            spare = pin in (11, 12)
            box(x, y, 80, 45, soft if spare else white, HexColor("#44A5F5") if pin == 1 else None, 6)
            circle(x + 15, y + 15, 9, signal_color)
            label(x + 15, y + 18.3, str(pin), 9.3, ink if pin in sd_pins[:2] else white, "GuideMono", "center")
            if pin == 1:
                label(x + 67, y + 17, "PIN 1", 8, clock_blue, "GuideBold", "right")
            label(x + 40, y + 35, name, 10, muted if spare else ink, "GuideBold", "center")
    rule(32, 377, 580, teal, 3)
    label(306, 393, "ZYBO PCB EDGE", 8.5, teal, "GuideBold", "center")

    pdf.restoreState()
    if hexagon:
        label(32, 361, "Protoboard layout", 16, ink, "GuideBold")
        label(334, 361, "One SD wire per mic", 16, ink, "GuideBold")
        box(32, 373, 285, 180, HexColor("#EDF5F2"), HexColor("#C3DCD5"), 8)
        label(45, 393, "Microphone side up", 10, teal, "GuideBold")

        for i, ((x_mm, y_mm), _) in enumerate(hexagon, start=1):
            x = 174 + 1.40 * x_mm
            y = 466 - 1.40 * y_mm
            color = sd_colors[i - 1]
            circle(x, y, 11, color)
            foreground = ink if i in (1, 2) else white
            label(x, y + 3, f"M{i}", 9, foreground, "GuideBold", "center")
            label(x, y + 24, f"JE{sd_pins[i - 1]}", 10, ink, "GuideMono", "center")

        box(297, 381, 12, 23, ink, radius=2)
        label(292, 396, "Harness", 8.5, teal, "GuideBold", "right")
        label(32, 571, "0° at M3 (right)  ·  270° below M4 and M5", 9.6, teal, "GuideBold")

        box(334, 373, 246, 180, white, border, 8)
        label(346, 391, "SD LEAD", 8, muted, "GuideBold")
        label(413, 391, "POSITION", 8, muted, "GuideBold")
        label(567, 391, "JE SOCKET", 8, muted, "GuideBold", "right")
        for i, (_, position) in enumerate(hexagon, start=1):
            y = 397 + 25 * (i - 1)
            if i % 2:
                box(340, y, 234, 23, soft, radius=4)
            circle(349, y + 11.5, 3, sd_colors[i - 1])
            label(358, y + 15, f"M{i} SD", 10.5, ink, "GuideBold")
            label(413, y + 15, position, 10.5)
            label(567, y + 15, f"JE{sd_pins[i - 1]}", 11, ink, "GuideMono", "right")

        label(32, 604, "Shared by all six microphones", 16, ink, "GuideBold")
        box(32, 615, 548, 69, soft, border, 7)
        shared = [
            (93, "VDD / 3V3", "JE6 · 3.3 V", red),
            (202, "GND", "JE5 · GND", ink),
            (306, "SCK / BCLK", f"JE{ports['i2s_sck']}", clock_blue),
            (413, "WS / LRCLK", f"JE{ports['i2s_ws']}", clock_green),
            (521, "L/R / SEL", "GND rail · JE5", muted),
        ]
        for x, pad, destination, color in shared:
            label(x, 638, pad, 10.2, muted, "GuideBold", "center")
            label(x, 664, destination, 11.2, color, "GuideBold", "center")

        label(32, 710, "Follow the printed pad labels on each module. Keep all six SD wires separate.", 10.6, ink, "GuideBold")
        label(32, 727, "With power disconnected, check for a 3.3 V to GND short and trace each SD wire to its JE socket.", 10, muted)
    else:
        left = 32
        right = 368
        label(left, 427, "Shared connections", 16, ink, "GuideBold")
        label(right, 427, "One SD wire per mic", 16, ink, "GuideBold")

        box(left, 441, 320, 200, white, border, 9)
        box(right, 441, 212, 200, white, border, 9)
        label(46, 461, "MICROPHONE BUNDLE", 8.4, muted, "GuideBold")
        label(338, 461, "PLUG INTO", 8.4, muted, "GuideBold", "right")
        label(383, 461, "SD / DOUT LEAD", 8.4, muted, "GuideBold")
        label(565, 461, "JE SOCKET", 8.4, muted, "GuideBold", "right")

        common = [
            ("VDD / 3V3", "JE6  (+3.3 V)", red),
            ("GND", "JE5  (GND)", ink),
            ("SCK / BCLK", f"JE{ports['i2s_sck']}", clock_blue),
            ("WS / LRCLK", f"JE{ports['i2s_ws']}", clock_green),
            ("L/R / SEL on every mic", "GND rail  (JE5)", muted),
        ]
        for index, (wire, destination, color) in enumerate(common):
            y = 474 + 31 * index
            if index % 2 == 0:
                box(41, y, 302, 28, soft, radius=4)
            circle(51, y + 14, 3.5, color)
            label(61, y + 18, wire, 11, ink, "GuideBold")
            label(335, y + 18, destination, 11.5, ink, "GuideBold", "right")

        for i, color in enumerate(sd_colors, start=1):
            y = 472 + 26 * (i - 1)
            if i % 2:
                box(377, y, 194, 24, soft, radius=4)
            circle(387, y + 12, 3.5, color)
            label(398, y + 16, f"MIC {i} SD", 11, ink, "GuideBold")
            label(562, y + 16, f"JE{ports[f'mic{i}_sd']}", 11.5, ink, "GuideMono", "right")

        box(32, 659, 548, 68, HexColor("#EAF4F2"), HexColor("#C8E2DA"), 9)
        label(46, 681, "Use the labels printed on each microphone board.", 11.5, teal, "GuideBold")
        label(46, 700, "Each SD gets a separate breadboard strip. With power disconnected, check", 10.2, ink)
        label(46, 714, "that VDD and GND are isolated and that the six SD strips are isolated.", 10.2, ink)

    rule(32, 747, 580)
    label(32, 767, "PINOUT REFERENCES", 8.0, muted, "GuideBold")
    x = source(142, 767, "Digilent Zybo Z7 board manual",
               "https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf")
    source(x + 16, 767, "Digilent Zybo Z7 master XDC", "https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc")
    label(580, 767, "3.3 V ONLY", 8.5, muted, "GuideBold", "right")

    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    # Run from the project root: python -m scripts.draw_je_connector_guide
    from radar.localization import HEX_LOCATIONS, HEX_PORTS_MM

    root = Path(__file__).resolve().parents[1]
    output = root / "wiring/six_microphone_hexagon_plug_in_guide.pdf"
    draw_connector_guide(output, six_channel_je_ports(root), hexagon=tuple(zip(HEX_PORTS_MM, HEX_LOCATIONS)))
    print(output)
