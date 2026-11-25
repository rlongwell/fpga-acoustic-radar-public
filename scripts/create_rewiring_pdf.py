"""Create the position-first guide and its standalone connector page.

Run with the bundled artifact Python (reportlab and pypdf).
"""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter
from draw_je_connector_guide import draw_connector_guide, six_channel_je_ports

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / "tmp/pdfs"
OUT = ROOT / "wiring/six_microphone_rewiring_guide.pdf"
TEMP.mkdir(parents=True, exist_ok=True)
ports = six_channel_je_ports(ROOT)
pins = [ports[f"mic{i}_sd"] for i in range(1, 7)]
connector = ROOT / "wiring/six_microphone_plug_in_guide.pdf"
draw_connector_guide(connector, ports)
for name, file in (("DejaVu", "DejaVuSans.ttf"), ("DejaVu-Bold", "DejaVuSans-Bold.ttf")):
    pdfmetrics.registerFont(TTFont(name, "/usr/share/fonts/truetype/dejavu/" + file))
c = canvas.Canvas(str(TEMP / "rewiring_cover.pdf"), pagesize=(612, 792))
ink, teal, muted = map(HexColor, ("#162b3b", "#00756f", "#526675"))


def text(x, y, value, size=10, bold=False, color=ink, center=False):
    c.setFillColor(color)
    c.setFont("DejaVu-Bold" if bold else "DejaVu", size)
    (c.drawCentredString if center else c.drawString)(x, y, value)


def box(x, y, w, h, fill, stroke=None):
    c.setFillColor(HexColor(fill))
    c.setStrokeColor(HexColor(stroke or fill))
    c.roundRect(x, y, w, h, 8, fill=1, stroke=bool(stroke))


c.setFillColor(ink)
c.rect(0, 691, 612, 101, fill=1, stroke=0)
text(32, 760, "ACOUSTIC RADAR / ZYBO Z7-20", 10, True, HexColor("#a9dcd6"))
text(32, 725, "Wire your 2 x 3 microphone array", 22, True, white)
text(32, 706, f"Six-channel FPGA build  |  MIC1 at JE{pins[0]}, MIC3 at JE{pins[2]}", 10.5, color=white)
box(32, 637, 548, 40, "#fff4e3", "#e9bf79")
text(45, 660, "POWER OFF: switch off and unplug the Zybo before rewiring.", 10.5, True)
text(45, 645, "3.3 V only. Never join the 3.3 V rail to ground.", 10)

text(32, 613, "1. Label the microphones in this top-down layout", 13, True)
text(32, 596, "These are microphone positions, not the six pads on a module.", 9, color=muted)
colors = ("#cf9c00", "#cf6c1c", "#8640b4", "#008c8c", "#416e9b", "#a85865")
xs = (102, 246, 390)
for i in range(6):
    x, y = xs[i % 3], 553 if i < 3 else 453
    c.setFillColor(HexColor("#f2f6f7"))
    c.setStrokeColor(HexColor(colors[i]))
    c.setLineWidth(2)
    c.circle(x, y, 27, fill=1, stroke=1)
    text(x, y - 9, str(i + 1), 26, True, center=True)
    text(x, y - 48, f"SD -> JE{pins[i]}", 12, True, center=True)
text(246, 386, "YOU / near edge: lower row is 4 - 5 - 6", 10, True, teal, True)
box(493, 476, 64, 78, "#e8f4f1", "#00756f")
text(525, 523, "PHONE", 9, True, teal, True)
text(525, 505, "MUSIC", 9, True, teal, True)
text(525, 484, "RIGHT", 9, True, teal, True)
text(525, 458, "Radar 90 deg", 8, True, teal, True)

text(32, 354, "2. Connect the six separate SD wires", 13, True)
positions = ("upper-left", "upper-middle", "upper-right", "lower-left", "lower-middle", "lower-right")
for i, position in enumerate(positions):
    y = 326 - i * 23
    if i in (0, 2):
        box(32, y - 6, 285, 22, "#e8f4f1")
    text(41, y, f"MIC{i + 1} / {position}", 10, i in (0, 2))
    text(270, y, f"JE{pins[i]}", 10, True)
text(339, 331, "Shared by ALL six mics", 10.5, True)
for i, (label, pin) in enumerate((("VDD / 3V3", "JE6"), ("GND", "JE5"),
                                ("SCK / BCLK", f"JE{ports['i2s_sck']}"), ("WS / LRCLK", f"JE{ports['i2s_ws']}"),
                                ("L/R / SEL", "GND rail"))):
    y = 308 - i * 23
    text(339, y, label, 10)
    text(514, y, pin, 10, True)

box(32, 73, 548, 119, "#f2f6f7")
text(45, 173, "3. Check before reconnecting power", 12, True)
checks = (
    "Follow the printed pad labels on each module; do not assume its pad order.",
    f"Trace upper-left SD to JE{pins[0]} and upper-right SD to JE{pins[2]}. Keep all six SDs separate.",
    "With power unplugged, meter the rails for shorts and verify each SD route.",
    "The next page shows the JE socket orientation and every shared connection.",
    "After rewiring this way: leave 'Swap MIC4 / MIC5 positions' unchecked in the GUI.",
)
for i, line in enumerate(checks):
    text(45, 153 - i * 15, line, 9)
text(32, 48, "JE numbers mean physical socket numbers, not FPGA package pins.", 9, True)
text(32, 30, "Pinout checked against Digilent Zybo Z7 manual and Zybo-Z7-Master.xdc.", 8, color=muted)
text(580, 30, "1 / 2", 8, color=muted, center=True)
c.linkURL("https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf", (32, 25, 315, 40), relative=0)
c.linkURL("https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc", (315, 25, 550, 40), relative=0)
c.showPage()
c.save()
writer = PdfWriter()
writer.append(str(TEMP / "rewiring_cover.pdf"))
writer.append(str(connector))
writer.add_metadata({"/Title": "Six microphone rewiring guide - physical layout and Pmod JE", "/Author": "Acoustic radar project"})
with OUT.open("wb") as file:
    writer.write(file)
assert len(PdfReader(OUT).pages) == 2
print(OUT)
