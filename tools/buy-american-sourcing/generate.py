"""Seeded instance generator for the buy-american-sourcing task (dev only, never uploaded).

usage: python3 generate.py [--seed N] [--out TASKDIR] [--quiet]

Builds 50 end products for a small business bidding a GSA facility-supplies
set-aside. Most products are realistic filler; some are planted so that one
specific misreading of FAR Part 25 / clause 52.225-1 changes that product's
legal outcome. Each planted product is re-drawn until the misreading provably
changes the product-level answer (checked with bacore.Rules).
"""
import argparse
import copy
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bacore  # noqa: E402

SECRET_SEED = 61813

COUNTRY_DUTY = {"US": 0}

SUPPLIERS = [
    # id, name, country, kind
    ("INHOUSE", "Own plant fabrication and machine shop (Dayton, OH)", "US", "inhouse"),
    ("SUP-01", "Great Lakes Steel Service Center (Cleveland, OH)", "US", "steel"),
    ("SUP-02", "Ohio Valley Tube and Roll Forming (Wheeling, WV)", "US", "steel"),
    ("SUP-03", "Hanbit Steel Trading Co. (Busan)", "KR", "steel"),
    ("SUP-04", "Gulf Coast Metals Processing (Houston, TX)", "US", "steel"),
    ("SUP-05", "Northland Galvanizing and Coil (Hamilton, ON)", "CA", "steel"),
    ("SUP-06", "Monterrey Metal Fabricators S.A. de C.V.", "MX", "steel"),
    ("SUP-07", "Midwest Fastener Supply (Rockford, IL)", "US", "fastener"),
    ("SUP-08", "Formosa Precision Fasteners Ltd. (Kaohsiung)", "TW", "fastener"),
    ("SUP-09", "Carolina Plastics Molding (Greenville, SC)", "US", "generic"),
    ("SUP-10", "Shenzhen Brightway Industrial Co.", "CN", "generic"),
    ("SUP-11", "Saigon Rubber and Plastics JSC", "VN", "generic"),
    ("SUP-12", "Bajio Componentes Industriales", "MX", "generic"),
    ("SUP-13", "Keystone Electronics Assembly (Allentown, PA)", "US", "electronic"),
    ("SUP-14", "Hsinchu Circuit Works Co.", "TW", "electronic"),
    ("SUP-15", "Pacific Components Brokerage (Irvine, CA)", "UNKNOWN", "broker"),
    ("SUP-16", "Kanto Quartz Devices K.K.", "JP", "listed"),
    ("SUP-17", "Ceylon Natural Rubber Exports (Pvt) Ltd.", "LK", "listed"),
    ("SUP-18", "Guangdong Bristle and Brush Materials Co.", "CN", "listed"),
    ("SUP-19", "Rheinland Laborglas GmbH", "DE", "listed"),
    ("SUP-20", "Appalachian Hardwood Products (Beckley, WV)", "US", "generic"),
    ("SUP-21", "Delta Elastomers Inc. (Akron, OH)", "US", "generic"),
    ("SUP-26", "Finger Lakes Scientific Glass (Elmira, NY)", "US", "generic"),
    ("SUP-22", "Dongguan Everlight Trading Co.", "CN", "import"),
    ("SUP-23", "Penang Industrial Exports Sdn. Bhd.", "MY", "import"),
    ("SUP-24", "Tianjin Hardware Export Corp.", "CN", "import"),
    ("SUP-25", "Hai Phong Manufacturing Co.", "VN", "import"),
]

# vendors not yet on the approved vendor list (need a paid qualification audit)
NEW_VENDORS = {"SUP-06", "SUP-09", "SUP-21", "SUP-23", "SUP-25"}

GENERIC_FOREIGN = ["SUP-10", "SUP-11", "SUP-12"]
US_GENERIC = ["SUP-09", "SUP-20", "SUP-21"]

# steel profiles: supplier, component_origin, ore, melt, roll, coat(None->NONE or coat country), price multiplier
STEEL_PROFILES = [
    ("SUP-01", "US", "US", "US", "US", "US", 1.00),
    ("SUP-02", "US", "BR", "US", "US", "US", 0.97),   # foreign ore, all processing in US
    ("SUP-03", "KR", "AU", "KR", "KR", "KR", 0.78),
    ("SUP-04", "US", "AU", "KR", "US", "US", 0.88),   # Korean slab, rolled and coated in US
    ("SUP-05", "CA", "US", "US", "US", "CA", 0.92),   # US melt and roll, galvanized in Canada
    ("SUP-06", "MX", "US", "US", "US", "US", 0.86),   # fabricated in Mexico from US steel
]


class Gen:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.offer_n = 0
        self.import_n = 0

    def r(self, a, b):
        return self.rng.randint(a, b)

    # ---------------- offer builders ----------------
    def _blank(self, pid, slot, sup, origin):
        self.offer_n += 1
        return dict(offer_id=f"tmp{self.offer_n}", product_id=pid, slot=slot, supplier_id=sup, supply_type="purchased",
                    component_origin=origin, material_class="", unit_price_cents="", freight_cents="",
                    duty_cents="", duty_free_certificate="", inhouse_direct_cents="",
                    inhouse_overhead_cents="", inhouse_profit_cents="", iron_steel_cost_cents="0",
                    cots_fastener="N", steel_ore_origin="", steel_melt_country="",
                    steel_rolling_country="", steel_coating_country="")

    def purchased(self, pid, slot, sup, origin, price, mclass="", cert=False, duty_rate=None):
        o = self._blank(pid, slot, sup, origin)
        frt = max(5, int(round(price * self.rng.uniform(0.02, 0.06))))
        if origin == "US":
            duty = 0
        else:
            rate = duty_rate if duty_rate is not None else self.rng.choice([0, 0.025, 0.034, 0.039, 0.045, 0.053, 0.065])
            duty = int(round(price * rate))
        o.update(unit_price_cents=str(price), freight_cents=str(frt), duty_cents=str(duty),
                 duty_free_certificate="Y" if (cert and duty > 0) else "N", material_class=mclass)
        return o

    def inhouse(self, pid, slot, direct, steel=None):
        o = self._blank(pid, slot, "INHOUSE", "US")
        oh = int(round(direct * self.rng.uniform(0.25, 0.45)))
        pr = int(round((direct + oh) * self.rng.uniform(0.10, 0.20)))
        o.update(supply_type="in_house", inhouse_direct_cents=str(direct),
                 inhouse_overhead_cents=str(oh), inhouse_profit_cents=str(pr))
        if steel:
            ore, melt, roll, coat, share = steel
            o.update(iron_steel_cost_cents=str(int(direct * share)), steel_ore_origin=ore,
                     steel_melt_country=melt, steel_rolling_country=roll, steel_coating_country=coat)
        return o

    def steel_offer(self, pid, slot, prof, base, coated=True):
        sup, origin, ore, melt, roll, coat, mult = prof
        price = int(base * mult * self.rng.uniform(0.95, 1.05))
        o = self.purchased(pid, slot, sup, origin, price, duty_rate=0.0 if origin == "US" else 0.0)
        cc = int(o["unit_price_cents"]) + int(o["freight_cents"]) + int(o["duty_cents"])
        o.update(iron_steel_cost_cents=str(cc), steel_ore_origin=ore, steel_melt_country=melt,
                 steel_rolling_country=roll, steel_coating_country=coat if coated else "NONE")
        return o

    def steel_slot(self, pid, slot, base, k=3, coated=True, profiles=None, inhouse=False):
        profs = profiles or self.rng.sample(STEEL_PROFILES, k)
        out = [self.steel_offer(pid, slot, p, base, coated) for p in profs]
        if inhouse:
            mprof = self.rng.choice([("US", "US", "US", "NONE"), ("AU", "KR", "KR", "NONE"), ("AU", "KR", "US", "NONE")])
            out.append(self.inhouse(pid, slot, int(base * self.rng.uniform(0.70, 0.85)), steel=mprof + (0.55,)))
        return out

    def fastener_slot(self, pid, slot, base):
        out = []
        for sup, origin, melt, mult in (("SUP-07", "US", "US", 1.0), ("SUP-08", "TW", "TW", 0.62)):
            price = int(base * mult * self.rng.uniform(0.95, 1.05))
            o = self.purchased(pid, slot, sup, origin, price, duty_rate=0.0 if origin == "US" else 0.034)
            cc = int(o["unit_price_cents"]) + int(o["freight_cents"]) + int(o["duty_cents"])
            o.update(iron_steel_cost_cents=str(cc), cots_fastener="Y", steel_ore_origin="AU" if melt != "US" else "US",
                     steel_melt_country=melt, steel_rolling_country=melt, steel_coating_country=melt)
            out.append(o)
        return out

    def generic_slot(self, pid, slot, base, k=2, us=None, mclass="", foreign=None, cert_p=0.25):
        out = []
        us = us or self.rng.choice(US_GENERIC)
        out.append(self.purchased(pid, slot, us, "US", int(base * self.rng.uniform(0.95, 1.08)), mclass=mclass))
        for sup in self.rng.sample(foreign or GENERIC_FOREIGN, k - 1):
            country = dict((s[0], s[2]) for s in SUPPLIERS)[sup]
            out.append(self.purchased(pid, slot, sup, country, int(base * self.rng.uniform(0.60, 0.85)),
                                      mclass=mclass, cert=self.rng.random() < cert_p))
        return out

    def electronic_slot(self, pid, slot, base, broker=True):
        out = [self.purchased(pid, slot, "SUP-13", "US", int(base * self.rng.uniform(0.95, 1.08))),
               self.purchased(pid, slot, "SUP-14", "TW", int(base * self.rng.uniform(0.62, 0.80)),
                              cert=self.rng.random() < 0.3)]
        if broker:
            out.append(self.purchased(pid, slot, "SUP-15", "UNKNOWN", int(base * self.rng.uniform(0.70, 0.86)),
                                      duty_rate=0.0))
        return out

    # ---------------- families ----------------
    def family(self, fam, pid):
        """Returns (product_row, bom_rows, offers, imports)."""
        R = self.r
        bom, offers = [], []

        def slot(name, desc, qty, offs):
            bom.append(dict(product_id=pid, slot=name, part_description=desc, qty_per_unit=str(qty)))
            offers.extend(offs)

        cots = "N"
        if fam == "shelving":
            desc = self.rng.choice(["Steel shelving unit, 5 shelf, 36 x 18 x 72 in", "Steel shelving unit, 6 shelf, 48 x 24 x 84 in",
                                    "Boltless rivet shelving, 4 shelf, 60 x 24 x 72 in", "Steel wire shelving, 4 shelf, 48 x 18 x 74 in"])
            slot("S1", "Upright post, roll-formed steel", 4, self.steel_slot(pid, "S1", R(1500, 2600), inhouse=self.rng.random() < 0.4))
            nsh = R(4, 6)
            slot("S2", "Shelf panel, cold-rolled steel sheet", nsh, self.steel_slot(pid, "S2", R(1900, 3100)))
            slot("S3", "Shelf clip and bolt set, per shelf", nsh, self.fastener_slot(pid, "S3", R(220, 420)))
            slot("S4", "Leveling foot, molded plastic", 4, self.generic_slot(pid, "S4", R(60, 140)))
            slot("S5", "Powder coat finish material", 1, self.generic_slot(pid, "S5", R(500, 900)))
            asm = R(2200, 4200); qty = R(60, 300)
        elif fam == "cabinet":
            desc = self.rng.choice(["Steel storage cabinet, 2 door, 36 x 18 x 72 in", "Flammable liquid safety cabinet, 30 gal",
                                    "Steel wardrobe cabinet, 36 x 24 x 78 in"])
            slot("S1", "Cabinet body, cold-rolled steel sheet", 1, self.steel_slot(pid, "S1", R(9000, 14000), inhouse=self.rng.random() < 0.5))
            slot("S2", "Door panel, cold-rolled steel sheet", 2, self.steel_slot(pid, "S2", R(2600, 3800)))
            slot("S3", "Hinge, latch and bolt hardware kit", 1, self.fastener_slot(pid, "S3", R(1200, 2200)))
            slot("S4", "Locking handle assembly", 1, self.generic_slot(pid, "S4", R(900, 1500)))
            slot("S5", "Powder coat finish material", 1, self.generic_slot(pid, "S5", R(900, 1500)))
            asm = R(4500, 7500); qty = R(40, 200)
        elif fam == "handtruck":
            desc = self.rng.choice(["Convertible hand truck, 600 lb", "Appliance hand truck, 800 lb",
                                    "Platform truck, 1200 lb, 24 x 48 in", "Stair-climbing hand truck, 500 lb"])
            slot("S1", "Frame, welded steel tube", 1, self.steel_slot(pid, "S1", R(3600, 5400), coated=False, inhouse=self.rng.random() < 0.5))
            slot("S2", "Pneumatic wheel, 10 in", 2, self.generic_slot(pid, "S2", R(1700, 2700), k=3))
            slot("S3", "Axle, steel bar", 1, self.steel_slot(pid, "S3", R(500, 950), k=2, coated=False))
            slot("S4", "Handle grip set", 1, self.generic_slot(pid, "S4", R(250, 450)))
            slot("S5", "Nose plate, steel", 1, self.steel_slot(pid, "S5", R(800, 1400), k=2))
            slot("S6", "Hardware kit", 1, self.fastener_slot(pid, "S6", R(150, 300)))
            asm = R(1500, 2800); qty = R(80, 400)
        elif fam == "brush":
            desc = self.rng.choice(["Push broom, 24 in, stiff fill", "Push broom, 36 in, medium fill",
                                    "Scrub brush, deck, 10 in", "Industrial floor brush, 18 in"])
            slot("S1", "Brush block, hardwood", 1, self.generic_slot(pid, "S1", R(300, 600), us="SUP-20"))
            fill = R(700, 1300)
            slot("S2", "Brush fill", 1, [
                self.purchased(pid, "S2", "SUP-18", "CN", int(fill * self.rng.uniform(0.55, 0.70)), mclass="hog bristles",
                               cert=self.rng.random() < 0.3),
                self.purchased(pid, "S2", "SUP-09", "US", int(fill * self.rng.uniform(0.95, 1.10)), mclass="polypropylene filament"),
                self.purchased(pid, "S2", "SUP-11", "VN", int(fill * self.rng.uniform(0.60, 0.75)), mclass="polypropylene filament")])
            slot("S3", "Handle, ash wood, 60 in", 1, self.generic_slot(pid, "S3", R(400, 700), us="SUP-20"))
            slot("S4", "Handle brace, steel", 1, self.steel_slot(pid, "S4", R(150, 260), k=2))
            asm = R(300, 700); qty = R(150, 600)
        elif fam == "mat":
            desc = self.rng.choice(["Anti-fatigue floor mat, 3 x 5 ft", "Anti-fatigue floor mat, 2 x 3 ft",
                                    "Drainage floor mat, 3 x 10 ft", "Entrance scraper mat, 4 x 6 ft"])
            rub = R(2400, 4200)
            slot("S1", "Rubber compound", 1, [
                self.purchased(pid, "S1", "SUP-17", "LK", int(rub * self.rng.uniform(0.55, 0.70)), mclass="natural rubber, crude",
                               cert=self.rng.random() < 0.4),
                self.purchased(pid, "S1", "SUP-21", "US", int(rub * self.rng.uniform(0.95, 1.10)), mclass="synthetic rubber (SBR)"),
                self.purchased(pid, "S1", "SUP-11", "VN", int(rub * self.rng.uniform(0.60, 0.78)), mclass="synthetic rubber (SBR)",
                               cert=self.rng.random() < 0.4)])
            slot("S2", "Foam cushion core", 1, self.generic_slot(pid, "S2", R(800, 1500), k=3, cert_p=0.4))
            slot("S3", "Beveled edge strip", 4, self.generic_slot(pid, "S3", R(80, 160)))
            slot("S4", "Bonding adhesive", 1, self.generic_slot(pid, "S4", R(200, 400), cert_p=0.4))
            asm = R(700, 1400); qty = R(100, 500)
        elif fam == "timer":
            desc = self.rng.choice(["Programmable process timer, panel mount", "Digital cycle counter, DIN rail",
                                    "Irrigation zone controller, 12 zone", "HVAC time clock, 7 day"])
            slot("S1", "Printed circuit board assembly", 1, self.electronic_slot(pid, "S1", R(2400, 4200)))
            xt = R(150, 320)
            slot("S2", "Quartz crystal, 32.768 kHz", 1, [
                self.purchased(pid, "S2", "SUP-16", "JP", int(xt * self.rng.uniform(0.45, 0.60)), mclass="quartz crystals"),
                self.purchased(pid, "S2", "SUP-13", "US", int(xt * self.rng.uniform(0.95, 1.10)), mclass="quartz crystals")])
            slot("S3", "Enclosure, molded polycarbonate", 1, self.generic_slot(pid, "S3", R(600, 1000)))
            slot("S4", "LCD display module", 1, self.electronic_slot(pid, "S4", R(900, 1500), broker=self.rng.random() < 0.5))
            slot("S5", "Output relay", 2, self.generic_slot(pid, "S5", R(300, 600), k=3, cert_p=0.4))
            slot("S6", "Wiring harness", 1, self.generic_slot(pid, "S6", R(300, 600)))
            asm = R(1200, 2400); qty = R(80, 400)
        elif fam == "led":
            desc = self.rng.choice(["LED high-bay fixture, 150 W", "LED troffer, 2 x 4 ft, 40 W",
                                    "LED wall pack, 80 W", "LED vapor-tight fixture, 4 ft"])
            slot("S1", "LED driver", 1, self.electronic_slot(pid, "S1", R(2200, 3600)))
            slot("S2", "LED board", 1, self.electronic_slot(pid, "S2", R(1800, 3000), broker=False))
            hs = R(1400, 2400)
            slot("S3", "Heat sink, extruded aluminum", 1, [
                self.inhouse(pid, "S3", int(hs * self.rng.uniform(0.80, 0.95))),
                self.purchased(pid, "S3", "SUP-12", "MX", int(hs * self.rng.uniform(0.70, 0.85)), cert=self.rng.random() < 0.3)])
            slot("S4", "Lens, polycarbonate", 1, self.generic_slot(pid, "S4", R(500, 900)))
            slot("S5", "Mounting bracket, steel", 1, self.steel_slot(pid, "S5", R(300, 600), k=2))
            asm = R(1000, 2000); qty = R(100, 500)
        elif fam == "charger":
            desc = self.rng.choice(["Forklift battery charger, 48 V, 85 A", "Battery charger, 24 V, 40 A",
                                    "Floor scrubber battery charger, 36 V", "Golf cart battery charger, 48 V"])
            slot("S1", "Power transformer", 1, self.generic_slot(pid, "S1", R(6000, 9500), k=3, cert_p=0.3))
            slot("S2", "Control board", 1, self.electronic_slot(pid, "S2", R(4000, 6500)))
            slot("S3", "Cabinet, aluminum sheet", 1, self.generic_slot(pid, "S3", R(2500, 3800)))
            slot("S4", "Output cable set", 1, self.generic_slot(pid, "S4", R(900, 1500)))
            slot("S5", "Cooling fan", 1, self.generic_slot(pid, "S5", R(400, 800)))
            asm = R(2500, 4500); qty = R(30, 150)
        elif fam == "cots_kit":
            cots = "Y"
            desc = self.rng.choice(["First aid kit, 50 person, ANSI Class A", "Eyewash station, portable, 16 gal",
                                    "Spill kit, universal, 20 gal", "Emergency response kit, 25 person"])
            slot("S1", "Case, molded polypropylene", 1, self.generic_slot(pid, "S1", R(900, 1600), k=3))
            slot("S2", "Contents set", 1, self.generic_slot(pid, "S2", R(2500, 4500), k=3))
            slot("S3", "Wall mount bracket, steel", 1, self.steel_slot(pid, "S3", R(200, 400), k=2))
            slot("S4", "Labels and instructions", 1, self.generic_slot(pid, "S4", R(100, 250)))
            asm = R(500, 1100); qty = R(100, 500)
        elif fam == "cots_steel":
            cots = "Y"
            desc = self.rng.choice(["Steel tool chest, 26 in, 5 drawer", "Steel roller cabinet, 41 in, 10 drawer",
                                    "Steel parts bin cabinet, 60 drawer", "Steel workbench, 72 in"])
            slot("S1", "Body, cold-rolled steel sheet", 1, self.steel_slot(pid, "S1", R(7000, 11000)))
            slot("S2", "Drawer, steel sheet", R(5, 10), self.steel_slot(pid, "S2", R(900, 1500)))
            slot("S3", "Drawer slide hardware", 1, self.fastener_slot(pid, "S3", R(800, 1500)))
            slot("S4", "Caster, polyurethane", 4, self.generic_slot(pid, "S4", R(300, 600)))
            slot("S5", "Drawer liner set", 1, self.generic_slot(pid, "S5", R(300, 600)))
            asm = R(3000, 5000); qty = R(40, 200)
        elif fam == "slides":
            desc = self.rng.choice(["Prepared microscope slide set, histology, 50 slides", "Blank slide kit with cover glass, 144 slides",
                                    "Prepared microscope slide set, botany, 25 slides"])
            slot("S1", "Glass microscope slides", 1, [
                self.purchased(pid, "S1", "SUP-19", "DE", R(900, 1300), mclass="glass microscope slides"),
                self.purchased(pid, "S1", "SUP-26", "US", R(1300, 1800), mclass="glass microscope slides")])
            slot("S2", "Cover glass", 1, [
                self.purchased(pid, "S2", "SUP-19", "DE", R(500, 800), mclass="cover glass, microscope slide"),
                self.purchased(pid, "S2", "SUP-26", "US", R(800, 1200), mclass="cover glass, microscope slide")])
            slot("S3", "Staining reagent set", 1, self.generic_slot(pid, "S3", R(800, 1400)))
            slot("S4", "Slide storage box", 1, self.generic_slot(pid, "S4", R(300, 600)))
            asm = R(1500, 3000); qty = R(50, 250)
        else:
            raise ValueError(fam)
        prod = dict(product_id=pid, description=desc, quantity=str(qty), cots_item=cots,
                    assembly_cost_cents=str(asm))
        return prod, bom, offers, []

    def add_import(self, part, pid, eval_cents):
        sup = self.rng.choice(["SUP-22", "SUP-23", "SUP-24", "SUP-25"])
        country = dict((s[0], s[2]) for s in SUPPLIERS)[sup]
        frt = int(eval_cents * self.rng.uniform(0.03, 0.06))
        duty = int(eval_cents * self.rng.choice([0.0, 0.025, 0.035, 0.05]))
        price = eval_cents - frt - duty
        self.import_n += 1
        part["imports"] = [dict(offer_id=f"tmpF{self.import_n}", product_id=pid, supplier_id=sup, country_of_manufacture=country,
                                unit_price_cents=str(price), freight_cents=str(frt), duty_cents=str(duty))]


# ---------------- product-level checks ----------------

def mini_inst(params, part):
    prod, bom, offers, imports = part["prod"], part["bom"], part["offers"], part["imports"]
    pid = prod["product_id"]
    by_slot = {}
    for o in offers:
        by_slot.setdefault((pid, o["slot"]), []).append(o)
    return dict(params=params, suppliers={}, products={pid: prod}, bom={pid: bom}, offers={},
                by_slot=by_slot, imports={}, imports_by_product={pid: imports} if imports else {})


def bkey(b):
    return ("imp", b["import_offer"]) if b["build"] == "import" else tuple(sorted(b["offers"].items()))


QUAL = set()  # suppliers already qualified; set in build() before planting


def view(params, part, flags=()):
    inst = mini_inst(params, part)
    pid = part["prod"]["product_id"]
    R = bacore.Rules(inst, flags)
    blds = R.builds(pid)
    st, info = R.admissibility(pid, blds)
    al = [b for b in blds if bacore.allowed(st, b)]
    alq = [b for b in al if b["suppliers"] <= QUAL]
    best = min(alq, key=lambda b: b["unit_outlay"]) if alq else None
    return dict(status=st, info=info, builds=blds, allowed={bkey(b) for b in al}, best=best)


def effect(params, part, flag):
    """True if the shortcut changes this product's answer (illegal pick or dearer optimum)."""
    t = view(params, part)
    s = view(params, part, (flag,))
    if t["best"] is None or s["best"] is None:
        return False
    if bkey(s["best"]) not in t["allowed"]:
        return True
    return s["best"]["unit_outlay"] > t["best"]["unit_outlay"]


def sane(params, part):
    t = view(params, part)
    blds = t["builds"]
    if not any(b["track"] != "foreign" for b in blds):
        return False
    L = min(b["unit_eval"] for b in blds)
    if len([b for b in blds if b["unit_eval"] == L]) != 1:
        return False
    outs = sorted(b["unit_outlay"] for b in blds if bkey(b) in t["allowed"])
    return len(outs) < 2 or outs[0] != outs[1]


def lowest_domestic(params, part):
    t = view(params, part)
    return min((b for b in t["builds"] if b["track"] != "foreign"), key=lambda b: b["unit_eval"])


# ---------------- planting ----------------

def plant(g, params, fam, pid, flag, tweak=None, tries=4000):
    for _ in range(tries):
        prod, bom, offers, imports = g.family(fam, pid)
        part = dict(prod=prod, bom=bom, offers=offers, imports=imports)
        if tweak and not tweak(g, params, part):
            continue
        if sane(params, part) and effect(params, part, flag):
            return part
    raise RuntimeError(f"could not plant {flag} in {fam}")


def tw_import_ratio(lo, hi):
    """Add a finished import whose evaluated price sits so that D / L is in [lo, hi]."""
    def f(g, params, part):
        D = lowest_domestic(params, part)["unit_eval"] if any(
            b["track"] != "foreign" for b in view(params, part)["builds"]) else None
        if D is None:
            return False
        g.add_import(part, part["prod"]["product_id"], int(D / g.rng.uniform(lo, hi)))
        return True
    return f


def tw_eval_tie(g, params, part):
    """Make lowest domestic evaluated cost exactly 130% of the import's (tie at the 30% factor)."""
    v = view(params, part)
    if not any(b["track"] != "foreign" for b in v["builds"]):
        return False
    D = lowest_domestic(params, part)["unit_eval"]
    bump = (-D) % 13
    part["prod"]["assembly_cost_cents"] = str(int(part["prod"]["assembly_cost_cents"]) + bump)
    D2 = lowest_domestic(params, part)["unit_eval"]
    if D2 % 13:
        return False
    L = D2 * 10 // 13
    g.add_import(part, part["prod"]["product_id"], L)
    imp = part["imports"][0]
    tot = int(imp["unit_price_cents"]) + int(imp["freight_cents"]) + int(imp["duty_cents"])
    imp["unit_price_cents"] = str(int(imp["unit_price_cents"]) + L - tot)
    return True


def tw_exact_ratio(num, den):
    """Pick a cheap US build whose domestic share is just under num/den and nudge one
    US-origin qty-1 purchased offer in it so the share becomes exactly num/den."""
    def f(g, params, part):
        v = view(params, part)
        us = sorted((b for b in v["builds"] if b["build"] == "us"), key=lambda x: x["unit_outlay"])
        qty = {r["slot"]: int(r["qty_per_unit"]) for r in part["bom"]}
        for b in us:
            T, Dm = b["cost_of_components"], b["domestic_component_cost"]
            if not (0.60 * T < Dm < num * T / den):
                continue
            chosen = [o for o in part["offers"] if b["offers"].get(o["slot"]) == o["offer_id"]]
            cand = [o for o in chosen if o["component_origin"] == "US" and qty[o["slot"]] == 1
                    and o["supply_type"] == "purchased" and o["iron_steel_cost_cents"] == "0"]
            for o in cand:
                x0 = int(o["unit_price_cents"]) + int(o["freight_cents"])
                T0, Dm0 = T - x0, Dm - x0
                top = num * T0 - den * Dm0
                if top <= 0 or top % (den - num):
                    continue
                x = top // (den - num)
                price = x - int(o["freight_cents"])
                if price <= 0 or abs(price - int(o["unit_price_cents"])) > 0.35 * int(o["unit_price_cents"]):
                    continue
                o["unit_price_cents"] = str(price)
                return True
        return False
    return f


def tw_pred_tie(g, params, part):
    """Nudge one non-steel purchased offer of a cheap US build so that build's iron and
    steel content is exactly 50% of its cost of components."""
    v = view(params, part)
    us = sorted((b for b in v["builds"] if b["build"] == "us"), key=lambda x: x["unit_outlay"])
    qty = {r["slot"]: int(r["qty_per_unit"]) for r in part["bom"]}
    for b in us:
        T, IS = b["cost_of_components"], b["iron_steel_cost"]
        if not (0.40 * T < IS < 0.60 * T):
            continue
        chosen = [o for o in part["offers"] if b["offers"].get(o["slot"]) == o["offer_id"]]
        for o in chosen:
            if o["iron_steel_cost_cents"] != "0" or o["supply_type"] != "purchased":
                continue
            q = qty[o["slot"]]
            fd = int(o["freight_cents"]) + int(o["duty_cents"])
            x0 = int(o["unit_price_cents"]) + fd
            need = 2 * IS - (T - q * x0)
            if need <= 0 or need % q:
                continue
            price = need // q - fd
            if price <= 0 or abs(price - int(o["unit_price_cents"])) > 0.35 * int(o["unit_price_cents"]):
                continue
            o["unit_price_cents"] = str(price)
            return True
    return False


def chain(*fs):
    def f(g, params, part):
        return all(fn(g, params, part) for fn in fs)
    return f


PLAN = [
    # (family, shortcut it must defeat, tweak)
    ("timer", "nonstrict", chain(tw_exact_ratio(3, 4), tw_import_ratio(1.05, 1.25))),
    ("timer", "stale_threshold", tw_import_ratio(1.05, 1.25)),
    ("led", "stale_threshold", tw_import_ratio(1.05, 1.25)),
    ("timer", "unknown_domestic", tw_import_ratio(1.05, 1.25)),
    ("led", "unknown_domestic", tw_import_ratio(1.05, 1.25)),
    ("mat", "cert_no_duty", tw_import_ratio(1.05, 1.25)),
    ("led", "cert_no_duty", tw_import_ratio(1.05, 1.25)),
    ("brush", "ignore_list", tw_import_ratio(1.05, 1.25)),
    ("mat", "ignore_list", tw_import_ratio(1.05, 1.25)),
    ("slides", "ignore_list", tw_import_ratio(1.05, 1.25)),
    ("timer", "ignore_notice", tw_import_ratio(1.05, 1.25)),
    ("cots_kit", "no_cots_waiver", tw_import_ratio(1.05, 1.25)),
    ("cots_kit", "no_cots_waiver", tw_import_ratio(1.05, 1.25)),
    ("cots_steel", "cots_waives_steel", tw_import_ratio(1.05, 1.25)),
    ("shelving", "count_fasteners", tw_import_ratio(1.05, 1.25)),
    ("cabinet", "count_fasteners", tw_import_ratio(1.05, 1.25)),
    ("shelving", "melt_only", tw_import_ratio(1.05, 1.25)),
    ("cabinet", "last_process", tw_import_ratio(1.05, 1.25)),
    ("shelving", "ore_matters", tw_import_ratio(1.05, 1.25)),
    ("handtruck", "steel_is_component_origin", tw_import_ratio(1.05, 1.25)),
    ("handtruck", "nonstrict", chain(tw_pred_tie, tw_import_ratio(1.05, 1.25))),
    ("led", "factor20", tw_import_ratio(1.21, 1.29)),
    ("charger", "factor20", tw_import_ratio(1.21, 1.29)),
    ("led", "tie_foreign", tw_eval_tie),
    ("charger", "no_fallback", tw_import_ratio(1.35, 1.9)),
    ("charger", "no_fallback", tw_import_ratio(1.35, 1.9)),
    ("led", "profit_in_cost", tw_import_ratio(1.05, 1.25)),
    ("timer", "assembly_in_cost", tw_import_ratio(1.05, 1.25)),
]

FILLER = ["shelving", "shelving", "cabinet", "cabinet", "handtruck", "handtruck", "handtruck", "brush", "brush",
          "mat", "mat", "timer", "led", "led", "charger", "charger", "cots_kit", "cots_kit", "cots_steel",
          "cots_steel", "slides", "brush"]


def build(seed, quiet=False):
    g = Gen(seed)
    params = {
        "solicitation": "FSS-26-0418, facility maintenance supplies, total small business set-aside",
        "contracting_agency": "General Services Administration, Federal Acquisition Service",
        "buy_american_clause": "FAR 52.225-1 Buy American-Supplies (Oct 2022), basic clause (no Alternate I)",
        "trade_agreements_apply": False,
        "offeror_size": "small",
        "delivery_calendar_year": 2029,
        "evaluation_date": "2026-12-01",
        "nonavailable_articles_available_domestically": ["Quartz crystals"],
        "qualification_budget_cents": 0,
    }
    QUAL.clear()
    fees = {}
    for sid, _, _, _ in SUPPLIERS:
        if sid in NEW_VENDORS:
            fees[sid] = g.rng.randint(25, 140) * 10000
        else:
            QUAL.add(sid)
    specs = [(f, fl, tw) for f, fl, tw in PLAN] + [(f, None, None) for f in FILLER]
    g.rng.shuffle(specs)
    parts = []
    for i, (fam, flag, tw) in enumerate(specs):
        pid = f"P{i + 1:02d}"
        if flag:
            part = plant(g, params, fam, pid, flag, tw)
        else:
            for _ in range(2000):
                prod, bom, offers, imports = g.family(fam, pid)
                part = dict(prod=prod, bom=bom, offers=offers, imports=imports)
                if g.rng.random() < 0.7:
                    tw_import_ratio(0.9, 1.7)(g, params, part)
                if sane(params, part):
                    break
        part["flag"] = flag
        pre = {"shelving": "SHV", "cabinet": "CAB", "handtruck": "HTK", "brush": "BRM", "mat": "MAT", "timer": "TMR",
               "led": "LED", "charger": "CHG", "cots_kit": "KIT", "cots_steel": "TCH", "slides": "SLD"}[fam]
        while True:
            item = f"{pre}-{g.rng.randint(1000, 9999)}"
            if item not in {p["prod"]["item_number"] for p in parts}:
                break
        part["prod"]["item_number"] = item
        parts.append(part)
    # final ids
    n = m_n = 0
    for part in parts:
        for o in part["offers"]:
            n += 1
            o["offer_id"] = f"C{n:04d}"
        for m in part["imports"]:
            m_n += 1
            m["offer_id"] = f"F{m_n:03d}"
    suppliers = []
    used = {o["supplier_id"] for p in parts for o in p["offers"]} | {m["supplier_id"] for p in parts for m in p["imports"]}
    for sid, name, country, kind in SUPPLIERS:
        if sid not in used:
            continue
        q = "Y" if sid in QUAL else "N"
        fee = fees.get(sid, 0)
        suppliers.append(dict(supplier_id=sid, name=name, country=country, qualified=q, qualification_fee_cents=str(fee)))
    return g, params, parts, suppliers


def write(task_dir, params, parts, suppliers):
    for sub in ("environment/data", "tests/data"):
        d = os.path.join(task_dir, sub)
        os.makedirs(d, exist_ok=True)
        json.dump(params, open(os.path.join(d, "params.json"), "w"), indent=2)

        def wcsv(name, rows, cols):
            with open(os.path.join(d, name), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
                w.writeheader()
                for r in rows:
                    w.writerow({c: r[c] for c in cols})
        wcsv("suppliers.csv", suppliers, ["supplier_id", "name", "country", "qualified", "qualification_fee_cents"])
        wcsv("products.csv", [p["prod"] for p in parts],
             ["product_id", "description", "item_number", "quantity", "cots_item", "assembly_cost_cents"])
        wcsv("bom.csv", [r for p in parts for r in p["bom"]], ["product_id", "slot", "part_description", "qty_per_unit"])
        ocols = ["offer_id", "product_id", "slot", "supplier_id", "supply_type", "component_origin", "material_class",
                 "unit_price_cents", "freight_cents", "duty_cents", "duty_free_certificate", "inhouse_direct_cents",
                 "inhouse_overhead_cents", "inhouse_profit_cents", "iron_steel_cost_cents", "cots_fastener",
                 "steel_ore_origin", "steel_melt_country", "steel_rolling_country", "steel_coating_country"]
        wcsv("component_offers.csv", [o for p in parts for o in p["offers"]], ocols)
        wcsv("finished_imports.csv", [m for p in parts for m in p["imports"]],
             ["offer_id", "product_id", "supplier_id", "country_of_manufacture", "unit_price_cents", "freight_cents", "duty_cents"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SECRET_SEED)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "tasks", "buy-american-sourcing"))
    ap.add_argument("--budget-frac", type=float, default=0.5)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    g, params, parts, suppliers = build(a.seed)
    tmp = os.path.join(a.out, "tests", "data")
    params["qualification_budget_cents"] = 10 ** 12
    write(a.out, params, parts, suppliers)
    inst = bacore.load(tmp)
    free = bacore.optimize(inst)
    need = bacore.optimize(inst, fees_only=True)["qualification_spend"]
    budget = need + int((free["qualification_spend"] - need) * a.budget_frac)
    budget = -(-budget // 10000) * 10000
    params["qualification_budget_cents"] = budget
    write(a.out, params, parts, suppliers)
    inst = bacore.load(tmp)
    sol = bacore.optimize(inst)
    out = bacore.to_output(inst, sol)
    json.dump(dict(total_outlay_cents=out["total_outlay_cents"], seed_note="generated by tools/buy-american-sourcing",
                   admissibility={l["product_id"]: l["admissibility"] for l in out["lines"]},
                   unbudgeted_total_outlay_cents=free["total_outlay"], unbudgeted_spend_cents=free["qualification_spend"]),
              open(os.path.join(a.out, "tests", "expected.json"), "w"), indent=2)
    if not a.quiet:
        print("min feasible spend", need, "budget", budget, "free spend", free["qualification_spend"], "free total", free["total_outlay"])
        print("optimum", sol["total_outlay"], "spend", sol["qualification_spend"], "new", sol["new_qualifications"])
        from collections import Counter
        print(Counter(sol["status"].values()))
        print(Counter(l["track"] for l in out["lines"]))
        print("planted:", sorted({p["flag"] for p in parts if p["flag"]}))


if __name__ == "__main__":
    main()
