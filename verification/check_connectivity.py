#!/usr/bin/env python3
"""Check the exported KiCad connectivity, JE XDC, connection table and SVG endpoints."""
import argparse
import csv
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
args = argparse.ArgumentParser(description=__doc__)
args.add_argument("--master-xdc", type=Path, help="Optional official Digilent Zybo-Z7-Master.xdc")
options = args.parse_args()

# Independent fixture from the Digilent manual, Figure 16.1 and Table 16.1.
je = {
    1: ("I2S_SCK", "V12", "output"),
    2: ("I2S_WS", "W16", "output"),
    3: ("MIC1_SD", "J15", "input"),
    4: ("MIC2_SD", "H15", "input"),
    5: ("GND", "", "power_out"),
    6: ("+3V3", "", "power_out"),
    7: ("MIC3_SD", "V13", "input"),
    8: ("MIC4_SD", "U17", "input"),
    9: ("NC", "T17", "passive+no_connect"),
    10: ("NC", "Y17", "passive+no_connect"),
    11: ("GND", "", "passive"),
    12: ("+3V3", "", "passive"),
}
data_pins = (3, 4, 7, 8)
fitted = set(range(1, 4))
all_mics = set(range(1, 5))

def check(ok, message):
    if not ok:
        raise SystemExit(f"FAIL: {message}")

def svg_groups(path, kind):
    return [
        g for g in ET.parse(root / "wiring" / path).getroot().iter()
        if g.get("data-kind") == kind
    ]

if options.master_xdc:
    src = options.master_xdc.read_text()
    block = src.split("##Pmod Header JE", 1)[1].split("##", 1)[0]
    digilent = {int(pin): loc for loc, pin in re.findall(
        r"PACKAGE_PIN\s+(\w+)\s+IOSTANDARD\s+LVCMOS33.*?Sch=je\[(\d+)\]", block
    )}
    check(digilent == {p: loc for p, (_, loc, _) in je.items() if loc}, "Digilent master JE pins and standards")
    print("PASS: all eight GPIO package pins match the supplied official Digilent master XDC")

csv_rows = {}
with (root / "docs/connection_table.csv").open(newline="") as fp:
    for row in csv.DictReader(fp):
        p = int(row["Physical connector pin"])
        check(row["Zybo connector"] == "JE" and p not in csv_rows, f"connection table JE{p}")
        csv_rows[p] = (row["Signal name"], row["FPGA package pin"].replace("—", ""))
check(csv_rows == {p: loc[:2] for p, loc in je.items()}, "connection table signals and pins")

src = (root / "constraints/zybo_z7_20_je_inmp441.xdc").read_text()
assign = re.findall(
    r"^(# )?set_property -dict \{ PACKAGE_PIN (\w+) IOSTANDARD (LVCMOS33)(.*?) \} "
    r"\[get_ports \{(\w+)\}\][ \t]*;[ \t]*# JE pin (\d+),", src, re.M
)
check(len(assign) == 6, "six XDC assignments including the commented optional port")
check(len(re.findall(r"^(?:# )?set_property", src, re.M)) == len(assign), "no unaudited XDC set_property lines")
check(len({x[1] for x in assign}) == len(assign), "package pins unique")
for opt, loc, standard, extra, name, p in assign:
    p = int(p)
    check((name, loc) == (je[p][0].lower(), je[p][1]), f"XDC JE{p} port and package")
    check(bool(opt) == (p == 8) and standard == "LVCMOS33", f"XDC JE{p} population and standard")
    check(extra == (" SLEW SLOW" if p in (1, 2) else ""), f"XDC JE{p} drive flags")
print("PASS: 12 connection-table rows; five active LVCMOS33 assignments and one optional")

nl = ET.parse(root / "schematic/zybo_je_inmp441.net.xml").getroot()
by_net = {}
by_je = {}
for net in nl.findall("nets/net"):
    name = net.get("name").removeprefix("/")
    nodes = net.findall("node")
    by_net[name] = {(n.get("ref"), n.get("pin")) for n in nodes}
    for n in nodes:
        if n.get("ref") == "J1":
            p = int(n.get("pin"))
            check(p not in by_je, f"multiple nets at J1:{p}")
            by_je[p] = (name if not name.startswith("unconnected-") else "NC", n.get("pintype"))
            if je[p][1]:
                check(n.get("pinfunction", "").endswith(je[p][1]), f"schematic pin function JE{p}")
check(by_je == {p: (a, c) for p, (a, _, c) in je.items()}, "schematic JE pin topology and directions")
expected = {
    "+3V3": {("J1", "6"), ("J1", "12")} | {(f"U{i}", "VDD") for i in all_mics} | {(f"C{i}", "1") for i in all_mics},
    "GND": {("J1", "5"), ("J1", "11")} | {(f"U{i}", p) for i in all_mics for p in ("GND", "L/R")}
           | {(f"{kind}{i}", "2") for i in all_mics for kind in "RC"},
    "I2S_SCK": {("J1", "1")} | {(f"U{i}", "SCK") for i in all_mics},
    "I2S_WS": {("J1", "2")} | {(f"U{i}", "WS") for i in all_mics},
    **{f"MIC{i}_SD": {("J1", str(p)), (f"R{i}", "1"), (f"U{i}", "SD")} for i, p in enumerate(data_pins, 1)},
}
nc = [by_net.pop(n) for n in tuple(by_net) if n.startswith("unconnected-")]
check(by_net == expected and {frozenset(n) for n in nc} == {frozenset({("J1", str(p))}) for p in (9, 10)},
      "exact expected net membership; no unexpected joins or missing pins")
comps = {c.get("ref"): c for c in nl.findall("components/comp")}
check(set(comps) == {"J1"} | {f"{k}{i}" for k in "URC" for i in all_mics}, "symbol population")
check({r for r,c in comps.items() if c.find('property[@name="dnp"]') is not None} == {"U4","R4","C4"}, "optional parts DNP")
for i in all_mics:
    check(comps[f"R{i}"].findtext("value") == "100k", f"R{i} pull-down")
    check(comps[f"C{i}"].findtext("value") == "100nF X7R", f"C{i} decoupling")
print("PASS: KiCad netlist has correct power, return, clock fanout, left selection, private SD and passive values")

faces = svg_groups("pmod_je_mating_face.svg", "je-socket")
grid = {}
for face in faces:
    p = int(face.get("data-je-pin"))
    key = (int(face.get("data-row")), int(face.get("data-column")))
    check(key not in grid and je[p][:2] == (face.get("data-net"), face.get("data-package")), f"mating face JE{p}")
    grid[key] = p
check(grid == {(r, c): p for r, row in enumerate(((6,5,4,3,2,1),(12,11,10,9,8,7)), 1)
               for c, p in enumerate(row, 1)}, "female socket orientation")
main = "wiring_three_microphones.svg"
feeds = svg_groups(main, "je-wire")
check(len(feeds) == 9 and {int(g.get("data-je-pin")): g.get("data-net") for g in feeds} ==
      {p: je[p][0] for p in (1,2,3,4,5,6,7,11,12)}, "three-mic JE harness feeds")

for path, mics in ((main, fitted), ("wiring_fourth_microphone.svg", {4})):
    expected_endpoints = {
        (str(i), pin, f"MIC{i}_SD" if pin == "SD" else net, str(data_pins[i-1]) if pin == "SD" else connector)
        for i in mics
        for pin, net, connector in (
            ("VDD","+3V3","6/12"),("GND","GND","5/11"),("L/R","GND","5/11"),
            ("SCK","I2S_SCK","1"),("WS","I2S_WS","2"),("SD","","")
        )
    }
    actual = [tuple(g.get(f"data-{k}") for k in ("mic","terminal","net","je-pin"))
              for g in svg_groups(path, "mic-terminal")]
    check(set(actual) == expected_endpoints and len(actual) == len(expected_endpoints), f"wiring endpoints: {path}")
print("PASS: 12 mating-face positions, nine populated JE feeds, and 24 microphone connections agree")
