"""Seeded instance generator for the buy-american-sourcing task, DoD version (dev only, never uploaded).

usage: python3 generate.py [--seed N] [--out TASKDIR] [--quiet]

50 end products for a small business bidding a DLA solicitation: tactical-vehicle and
weapon-system spare parts (specialty metals restricted), look-alike parts and facility supplies
(not restricted). Look-alike parts were once tied to forklifts, ground support equipment and COTS
vehicles; they now use the facility label so coverage never hinges on the automotive item definition.
Mounts carry a glass-sealed sight window whose Fe-Ni-Co frame is below the steel carbon range but is
still a specialty metal as an iron-nickel alloy.
Planted products are re-drawn until one specific misreading of DFARS / FAR provably changes
that product's answer (checked with bacore.Rules).
"""
import argparse
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bacore  # noqa: E402

SECRET_SEED = 70423

SUPPLIERS = [
    ("INHOUSE", "Own plant fabrication and machine shop (Dayton, OH)", "US"),
    ("SUP-01", "Great Lakes Steel Service Center (Cleveland, OH)", "US"),
    ("SUP-02", "Ohio Valley Tube and Roll Forming (Wheeling, WV)", "US"),
    ("SUP-03", "Hanbit Steel Trading Co. (Busan)", "KR"),
    ("SUP-04", "Gulf Coast Metals Processing (Houston, TX)", "US"),
    ("SUP-05", "Northland Galvanizing and Coil (Hamilton, ON)", "CA"),
    ("SUP-06", "Monterrey Metal Fabricators S.A. de C.V.", "MX"),
    ("SUP-07", "Midwest Fastener Supply (Rockford, IL)", "US"),
    ("SUP-08", "Formosa Precision Fasteners Ltd. (Kaohsiung)", "TW"),
    ("SUP-09", "Carolina Plastics Molding (Greenville, SC)", "US"),
    ("SUP-10", "Shenzhen Brightway Industrial Co.", "CN"),
    ("SUP-11", "Saigon Rubber and Plastics JSC", "VN"),
    ("SUP-12", "Bajio Componentes Industriales", "MX"),
    ("SUP-13", "Keystone Electronics Assembly (Allentown, PA)", "US"),
    ("SUP-14", "Hsinchu Circuit Works Co.", "TW"),
    ("SUP-15", "Pacific Components Brokerage (Irvine, CA)", "UNKNOWN"),
    ("SUP-16", "Kanto Quartz Devices K.K.", "JP"),
    ("SUP-17", "Ceylon Natural Rubber Exports (Pvt) Ltd.", "LK"),
    ("SUP-18", "Guangdong Bristle and Brush Materials Co.", "CN"),
    ("SUP-19", "Rheinland Laborglas GmbH", "DE"),
    ("SUP-20", "Appalachian Hardwood Products (Beckley, WV)", "US"),
    ("SUP-21", "Delta Elastomers Inc. (Akron, OH)", "US"),
    ("SUP-26", "Finger Lakes Scientific Glass (Elmira, NY)", "US"),
    ("SUP-27", "Kaohsiung Aerospace Fastener Corp.", "TW"),
    ("SUP-28", "Hamburg Industrie-Komponenten GmbH", "DE"),
    ("SUP-29", "Toronto Precision Plastics Ltd.", "CA"),
    ("SUP-30", "Allegheny Forge Works (Pittsburgh, PA)", "US"),
    ("SUP-31", "Pohang Precision Forging Co.", "KR"),
    ("SUP-32", "Pune Forge and Machine Pvt. Ltd.", "IN"),
    ("SUP-33", "Brescia Meccanica S.p.A.", "IT"),
    ("SUP-34", "Linz Antriebstechnik GmbH", "AT"),
    ("SUP-35", "Ningbo Rare Earth Magnetics Co.", "CN"),
    ("SUP-36", "Hokuriku Magnet Works K.K.", "JP"),
    ("SUP-37", "Mahoning Titanium Products (Niles, OH)", "US"),
    ("SUP-38", "Baoji Titanium Trading Co.", "CN"),
    ("SUP-39", "Delaware Valley Stainless (Chester, PA)", "US"),
    ("SUP-40", "Busan Stainless Sheet Co.", "KR"),
    ("SUP-50", "Buckeye Motor Works (Lima, OH)", "US"),
    ("SUP-54", "Great Plains Motion Supply (Wichita, KS)", "US"),
    ("SUP-51", "Ruhr Antriebe GmbH", "DE"),
    ("SUP-52", "Taichung Motion Components Co.", "TW"),
    ("SUP-53", "Wenzhou Lock and Hardware Co.", "CN"),
    ("SUP-22", "Dongguan Everlight Trading Co.", "CN"),
    ("SUP-23", "Penang Industrial Exports Sdn. Bhd.", "MY"),
    ("SUP-24", "Tianjin Hardware Export Corp.", "CN"),
    ("SUP-25", "Hai Phong Manufacturing Co.", "VN"),
    ("SUP-42", "Stuttgart Fahrzeugteile GmbH", "DE"),
    ("SUP-43", "Osaka Industrial Products Co.", "JP"),
    ("SUP-44", "Graz Systemtechnik GmbH", "AT"),
    ("SUP-45", "Ontario Defence Components Inc.", "CA"),
    ("SUP-46", "Changwon Defense Parts Co.", "KR"),
]
COUNTRY = {s[0]: s[2] for s in SUPPLIERS}
NEW_VENDORS = {"SUP-06", "SUP-09", "SUP-21", "SUP-23", "SUP-25", "SUP-28", "SUP-29", "SUP-33", "SUP-36", "SUP-44"}
GENERIC_FOREIGN = ["SUP-10", "SUP-11", "SUP-12", "SUP-28", "SUP-29"]
US_GENERIC = ["SUP-09", "SUP-20", "SUP-21"]
IMPORTERS = ["SUP-22", "SUP-23", "SUP-24", "SUP-25", "SUP-42", "SUP-43", "SUP-44", "SUP-45", "SUP-46"]

# material_id, name, base, max element percent
MATERIALS = [
    ("MAT-A36", "ASTM A36 structural carbon steel", "iron", dict(c="0.29", mn="1.20", si="0.40", cu="0.20")),
    ("MAT-1018", "AISI 1018 carbon steel", "iron", dict(c="0.20", mn="0.90", si="0.30")),
    ("MAT-1541", "AISI 1541 carbon steel", "iron", dict(c="0.44", mn="1.65", si="0.30")),
    ("MAT-1340", "AISI 1340 manganese steel", "iron", dict(c="0.43", mn="1.90", si="0.35")),
    ("MAT-A572", "ASTM A572 Grade 50 HSLA steel", "iron", dict(c="0.23", mn="1.35", si="0.40", nb="0.05", v="0.15")),
    ("MAT-4140", "AISI 4140 chromium-molybdenum steel", "iron", dict(c="0.43", mn="1.00", si="0.35", cr="1.10", mo="0.25")),
    ("MAT-4340", "AISI 4340 nickel-chromium-molybdenum steel", "iron", dict(c="0.43", mn="0.80", si="0.35", cr="0.90", mo="0.30", ni="2.00")),
    ("MAT-5160", "AISI 5160 spring steel", "iron", dict(c="0.64", mn="1.00", si="0.35", cr="0.90")),
    ("MAT-304", "AISI 304 stainless steel", "iron", dict(c="0.08", mn="2.00", si="0.75", cr="20.00", ni="10.50")),
    ("MAT-M19", "M19 non-oriented electrical steel", "iron", dict(c="0.01", mn="0.50", si="3.30", al="0.60")),
    ("MAT-6061", "6061-T6 aluminum alloy", "aluminum", dict(si="0.80", cu="0.40", cr="0.35", mg="1.20", fe="0.70")),
    ("MAT-TI64", "Ti-6Al-4V titanium alloy", "titanium", dict(al="6.75", v="4.50", fe="0.30")),
    ("MAT-SMCO", "Sintered samarium-cobalt (Sm2Co17) magnet alloy", "cobalt", dict(co="52.00", sm="25.50", fe="18.00", cu="6.00", zr="3.00")),
    ("MAT-C932", "C93200 bearing bronze", "copper", dict(cu="85.00", sn="8.00", pb="8.00", zn="4.00")),
    ("MAT-FNC", "Fe-29Ni-17Co glass-sealing alloy, low carbon", "iron", dict(c="0.01", mn="0.50", si="0.20", ni="29.50", co="17.80")),
]
ELEMENTS = ["c", "mn", "si", "cu", "al", "cr", "co", "mo", "ni", "nb", "ti", "w", "v", "fe", "mg", "sm", "zr", "sn", "pb", "zn"]

RESTRICTED = [k for k, v in bacore.RESTRICTED_USE.items() if v]
LOOKALIKE = ["10K all-terrain lifter, army system (ATLAS forklift)",
             "MB-4 aircraft tow tractor (aircraft ground support equipment)",
             "Commercial 3/4-ton pickup truck, base motor pool (COTS vehicle)"]
FACILITY = "Warehouse and facility use"
VEHICLES = ["M1083A1 FMTV 5-ton cargo truck", "M1151A1 HMMWV armament carrier", "M1126 Stryker infantry carrier vehicle"]
WEAPONS = ["M2A1 .50 caliber machine gun (crew-served weapon)", "M240B 7.62 mm machine gun (crew-served weapon)"]

OCOLS = ["offer_id", "product_id", "slot", "supplier_id", "supply_type", "component_origin", "material_class",
         "part_form", "component_cots", "unit_price_cents", "freight_cents", "duty_cents", "duty_free_certificate",
         "inhouse_direct_cents", "inhouse_overhead_cents", "inhouse_profit_cents", "iron_steel_cost_cents",
         "cots_fastener", "fastener_mfr_dod_certified", "metal_material", "metal_g_per_piece", "metal_ore_origin",
         "metal_melt_country", "metal_rolling_country", "metal_coating_country"]
STEEL_MATS = {"MAT-FNC", "MAT-M19", "MAT-A36", "MAT-1018", "MAT-1541", "MAT-1340", "MAT-A572", "MAT-4140", "MAT-4340", "MAT-5160", "MAT-304"}


class Gen:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.n = 0

    def r(self, a, b):
        return self.rng.randint(a, b)

    def u(self, a, b):
        return self.rng.uniform(a, b)

    def offer(self, pid, slot, sup, origin=None, price=0, form="nonmetal", mclass="", cert=False, duty_rate=None,
              cots="N", mat="", grams=0, ore="", melt="", roll="", coat="", fastener=False, dodcert="N"):
        self.n += 1
        origin = origin or COUNTRY[sup]
        o = {c: "" for c in OCOLS}
        o.update(offer_id=f"tmp{self.n}", product_id=pid, slot=slot, supplier_id=sup, supply_type="purchased",
                 component_origin=origin, material_class=mclass, part_form=form, component_cots=cots,
                 cots_fastener="Y" if fastener else "N", fastener_mfr_dod_certified=dodcert if fastener else "N",
                 iron_steel_cost_cents="0", metal_material=mat, metal_g_per_piece=str(grams) if mat else "")
        frt = max(5, int(round(price * self.u(0.02, 0.06))))
        if origin == "US":
            duty = 0
        else:
            rate = duty_rate if duty_rate is not None else self.rng.choice([0, 0.025, 0.034, 0.039, 0.045, 0.053])
            duty = int(round(price * rate))
        o.update(unit_price_cents=str(price), freight_cents=str(frt), duty_cents=str(duty),
                 duty_free_certificate="Y" if (cert and duty > 0) else "N")
        if mat:
            o.update(metal_ore_origin=ore or melt, metal_melt_country=melt, metal_rolling_country=roll or melt,
                     metal_coating_country=coat or "NONE")
            if mat in STEEL_MATS:
                cc = price + frt + duty
                # electronic parts only carry small stainless contacts or fittings
                o["iron_steel_cost_cents"] = str(int(cc * 0.03) if form == "electronic" else cc)
        return o

    def inhouse(self, pid, slot, direct, mat="", grams=0, melt="US", roll="US", ore="US", form="machined_part"):
        self.n += 1
        o = {c: "" for c in OCOLS}
        oh = int(round(direct * self.u(0.25, 0.45)))
        pr = int(round((direct + oh) * self.u(0.10, 0.20)))
        o.update(offer_id=f"tmp{self.n}", product_id=pid, slot=slot, supplier_id="INHOUSE", supply_type="in_house",
                 component_origin="US", part_form=form if mat else "nonmetal", component_cots="N",
                 inhouse_direct_cents=str(direct), inhouse_overhead_cents=str(oh), inhouse_profit_cents=str(pr),
                 iron_steel_cost_cents="0", cots_fastener="N", fastener_mfr_dod_certified="N",
                 metal_material=mat, metal_g_per_piece=str(grams) if mat else "")
        if mat:
            o.update(metal_ore_origin=ore, metal_melt_country=melt, metal_rolling_country=roll, metal_coating_country="NONE")
            if mat in STEEL_MATS:
                o["iron_steel_cost_cents"] = str(int(direct * 0.55))
        return o

    # ---- slot helpers ----
    def steel_sheet(self, pid, slot, base, grams, k=3, coated=True, mats=("MAT-A36", "MAT-1018"), inhouse=False):
        profs = [("SUP-01", "US", "US", "US", "US", 1.00), ("SUP-02", "US", "BR", "US", "US", 0.97),
                 ("SUP-03", "KR", "AU", "KR", "KR", 0.78), ("SUP-04", "US", "AU", "KR", "US", 0.88),
                 ("SUP-05", "CA", "US", "US", "US", 0.92), ("SUP-06", "MX", "US", "US", "US", 0.86)]
        out = []
        for sup, org, ore, melt, roll, mult in self.rng.sample(profs, k):
            coat = (COUNTRY[sup] if sup == "SUP-05" else roll) if coated else "NONE"
            out.append(self.offer(pid, slot, sup, org, int(base * mult * self.u(0.95, 1.05)), "fabricated_part",
                                  duty_rate=0.0, mat=self.rng.choice(mats), grams=grams, ore=ore, melt=melt, roll=roll,
                                  coat=coat))
        if inhouse:
            melt = self.rng.choice(["US", "KR", "JP"])
            out.append(self.inhouse(pid, slot, int(base * self.u(0.70, 0.85)), mat=self.rng.choice(mats), grams=grams,
                                    melt=melt, roll=melt, ore="AU" if melt != "US" else "US", form="fabricated_part"))
        return out

    def fasteners(self, pid, slot, base, grams, mat="MAT-1018"):
        out = []
        for sup, mult, cert in (("SUP-07", 1.0, "N"), ("SUP-08", 0.60, "N"), ("SUP-27", 0.72, "Y")):
            melt = "US" if sup == "SUP-07" else self.rng.choice(["TW", "CN"])
            out.append(self.offer(pid, slot, sup, None, int(base * mult * self.u(0.95, 1.05)), "fastener",
                                  duty_rate=0.0 if sup == "SUP-07" else 0.034, cots="Y", mat=mat, grams=grams,
                                  melt=melt, roll=melt, coat=melt, fastener=True, dodcert=cert))
        return out

    def generic(self, pid, slot, base, k=2, us=None, mclass="", foreign=None, cert_p=0.25):
        out = [self.offer(pid, slot, us or self.rng.choice(US_GENERIC), "US", int(base * self.u(0.95, 1.08)),
                          mclass=mclass)]
        for sup in self.rng.sample(foreign or GENERIC_FOREIGN, k - 1):
            out.append(self.offer(pid, slot, sup, None, int(base * self.u(0.60, 0.85)), mclass=mclass,
                                  cert=self.rng.random() < cert_p))
        return out

    def electronic(self, pid, slot, base, broker=True, sm_g=0):
        mat = "MAT-304" if sm_g else ""
        out = [self.offer(pid, slot, "SUP-13", "US", int(base * self.u(0.95, 1.08)), "electronic", mat=mat,
                          grams=sm_g, melt="US"),
               self.offer(pid, slot, "SUP-14", "TW", int(base * self.u(0.62, 0.80)), "electronic",
                          cert=self.rng.random() < 0.3, mat=mat, grams=sm_g, melt="CN")]
        if broker:
            out.append(self.offer(pid, slot, "SUP-15", "UNKNOWN", int(base * self.u(0.70, 0.86)), "electronic",
                                  duty_rate=0.0, mat=mat, grams=sm_g, melt="UNKNOWN"))
        return out

    def pick(self, choices, k):
        """first choice (the US baseline) always offered, plus k-1 others."""
        return [choices[0]] + self.rng.sample(choices[1:], k - 1)

    def assembly(self, pid, slot, sup, price, cots, items):
        """Purchased sub-assembly. items: (desc, qty, origin, form, mat, grams, melt, cost)."""
        o = self.offer(pid, slot, sup, None, price, "assembly", cots=cots, duty_rate=0.0 if COUNTRY[sup] == "US" else None)
        inner, ist = [], 0
        for k, (desc, q, org, form, mat, grams, melt, cost) in enumerate(items, 1):
            i_ist = cost if mat in STEEL_MATS else 0
            ist += q * i_ist
            inner.append(dict(item_no=str(k), description=desc, qty=str(q), item_origin=org, part_form=form,
                              component_cots="N", metal_material=mat, metal_g_per_piece=str(grams),
                              metal_melt_country=melt, metal_rolling_country=melt, metal_coating_country="NONE",
                              iron_steel_cost_cents=str(i_ist), unit_cost_cents=str(cost)))
        o["iron_steel_cost_cents"] = str(ist)
        o["_inner"] = inner
        return o

    def motor_offers(self, pid, slot):
        R = self.r
        base = R(4600, 6200)
        mg, lam, sh = R(50, 90), R(600, 900), R(70, 110)
        cm, cl, cs, cb = R(1800, 2800), R(500, 800), R(250, 450), R(300, 500)

        def items(mmelt, lmelt, smelt, morg=None, lorg=None, sorg=None):
            return [("Rotor magnet, SmCo", 1, morg or mmelt, "magnet", "MAT-SMCO", mg, mmelt, cm),
                    ("Stator lamination stack", 1, lorg or lmelt, "fabricated_part", "MAT-M19", lam, lmelt, cl),
                    ("Rotor shaft", 1, sorg or smelt, "machined_part", "MAT-304", sh, smelt, cs),
                    ("End bell pair, cast aluminum", 1, "US", "casting", "MAT-6061", 300, "US", cb)]
        opts = [
            ("SUP-50", 1.00, "N", items("JP", "US", "US", lorg="US", sorg="US")),
            ("SUP-50", 0.88, "N", items("CN", "US", "US")),
            ("SUP-50", 0.86, "N", items("JP", "KR", "KR")),
            ("SUP-52", 0.70, "Y", items("CN", "CN", "CN")),
            ("SUP-54", 0.74, "Y", items("CN", "CN", "CN")),
            ("SUP-52", 0.76, "Y", items("JP", "CN", "CN")),
            ("SUP-51", 0.90, "N", items("CN", "CN", "CN")),
            ("SUP-50", 0.94, "N", items("JP", "US", "KR")),
        ]
        pick = [opts[0]] + self.rng.sample(opts[1:], 3)
        return [self.assembly(pid, slot, sup, int(base * m * self.u(0.97, 1.03)), cots, it) for sup, m, cots, it in pick]

    def lock_offers(self, pid, slot):
        R = self.r
        base = R(1500, 2300)
        fg, pg, sg = R(400, 600), R(60, 100), R(15, 30)
        cf, cp, cs = R(600, 900), R(200, 320), R(40, 80)

        def items(fmelt, pmelt, smelt, org=None):
            return [("Lock body, forged", 1, org or fmelt, "forging", "MAT-4140", fg, fmelt, cf),
                    ("Plunger", 1, org or pmelt, "machined_part", "MAT-4340", pg, pmelt, cp),
                    ("Detent spring", 1, org or smelt, "machined_part", "MAT-5160", sg, smelt, cs)]
        opts = [
            ("SUP-30", 1.00, "N", items("US", "US", "US")),
            ("SUP-30", 0.82, "N", items("KR", "US", "US", org="US")),
            ("SUP-53", 0.65, "Y", items("CN", "CN", "CN")),
            ("SUP-33", 0.80, "N", items("CN", "CN", "CN", org="IT")),
        ]
        pick = [opts[0]] + self.rng.sample(opts[1:], 2)
        return [self.assembly(pid, slot, sup, int(base * m * self.u(0.97, 1.03)), cots, it) for sup, m, cots, it in pick]

    def sm_part(self, pid, slot, base, grams, form, choices):
        """choices: list of (supplier, material, melt, roll, mult, cots)."""
        out = []
        for sup, mat, melt, roll, mult, cots in choices:
            out.append(self.offer(pid, slot, sup, None, int(base * mult * self.u(0.95, 1.05)), form, cots=cots,
                                  duty_rate=0.0 if COUNTRY[sup] == "US" else None, mat=mat, grams=grams, melt=melt,
                                  roll=roll, ore="AU" if melt not in ("US", "UNKNOWN") else melt))
        return out

    # ---------------- families ----------------
    def family(self, fam, pid, use=None):
        R, bom, offers = self.r, [], []

        def slot(name, desc, qty, offs):
            bom.append(dict(product_id=pid, slot=name, part_description=desc, qty_per_unit=str(qty)))
            offers.extend(offs)

        cots = "N"
        use = use or FACILITY
        if fam == "battery_box":
            desc = self.rng.choice(["Battery box assembly, 2-battery", "Battery box assembly, 4-battery",
                                    "Battery tray and hold-down kit"])
            b = R(4200, 6200)
            slot("S1", "Box shell, formed sheet", 1, self.sm_part(pid, "S1", b, R(5200, 7800), "fabricated_part", self.pick([
                ("SUP-01", "MAT-6061", "US", "US", 1.00, "N"), ("SUP-10", "MAT-6061", "CN", "CN", 0.70, "N"),
                ("SUP-39", "MAT-304", "US", "US", 1.12, "N"), ("SUP-40", "MAT-304", "KR", "KR", 0.86, "N"),
                ("SUP-33", "MAT-304", "CN", "CN", 0.92, "N")], 3)))
            slot("S2", "Hold-down rod, threaded", 2, self.sm_part(pid, "S2", R(450, 800), R(300, 420), "mill_product", self.pick([
                ("SUP-01", "MAT-4140", "US", "US", 1.00, "N"), ("SUP-31", "MAT-4140", "KR", "KR", 0.78, "N"),
                ("SUP-10", "MAT-4140", "CN", "CN", 0.66, "Y"), ("SUP-03", "MAT-1541", "KR", "KR", 0.70, "N"),
                ("SUP-03", "MAT-1340", "KR", "KR", 0.68, "N"), ("SUP-12", "MAT-4140", "US", "MX", 0.62, "N")], 4)))
            slot("S3", "Fastener kit, stainless", 1, self.fasteners(pid, "S3", R(500, 900), R(150, 260), "MAT-304"))
            slot("S4", "Battery disconnect switch", 1, self.electronic(pid, "S4", R(1800, 2800), sm_g=R(150, 300)))
            slot("S5", "Lid gasket", 1, [
                self.offer(pid, "S5", "SUP-17", "LK", R(150, 260), mclass="natural rubber, crude", cert=self.rng.random() < 0.4),
                self.offer(pid, "S5", "SUP-21", "US", R(280, 420), mclass="synthetic rubber (SBR)")])
            asm = R(1200, 2400); qty = R(60, 260)
        elif fam == "hinge":
            desc = self.rng.choice(["Door hinge assembly, armored", "Hatch hinge assembly", "Tailgate hinge set"])
            b = R(2200, 3200)
            slot("S1", "Hinge leaf, forged", 2, self.sm_part(pid, "S1", b, R(1500, 2100), "forging", self.pick([
                ("SUP-30", "MAT-4140", "US", "US", 1.00, "N"), ("SUP-31", "MAT-4140", "KR", "KR", 0.76, "N"),
                ("SUP-32", "MAT-4140", "CN", "IN", 0.70, "N"), ("SUP-33", "MAT-4140", "CN", "IT", 0.82, "N"),
                ("SUP-10", "MAT-4140", "CN", "CN", 0.64, "Y")], 3)))
            slot("S2", "Hinge pin", 1, self.sm_part(pid, "S2", R(500, 900), R(30, 140), "machined_part", [
                ("SUP-39", "MAT-304", "US", "US", 1.00, "N"), ("SUP-38", "MAT-TI64", "CN", "CN", 0.66, "N"),
                ("SUP-37", "MAT-TI64", "US", "US", 1.20, "N")]))
            slot("S3", "Bushing, bronze", 2, self.sm_part(pid, "S3", R(200, 350), R(60, 90), "casting", [
                ("SUP-30", "MAT-C932", "US", "US", 1.00, "N"), ("SUP-10", "MAT-C932", "CN", "CN", 0.66, "N")]))
            slot("S4", "Grease fitting and bolt set", 1, self.fasteners(pid, "S4", R(300, 600), R(60, 160), "MAT-304"))
            asm = R(900, 1800); qty = R(80, 300)
        elif fam == "mount":
            desc = self.rng.choice(["Pintle mount assembly", "Cradle and pintle assembly", "Ring mount adapter"])
            b = R(7000, 10000)
            slot("S1", "Mount body, machined", 1, self.sm_part(pid, "S1", b, R(4000, 6000), "machined_part", self.pick([
                ("SUP-01", "MAT-6061", "US", "US", 1.00, "N"), ("SUP-10", "MAT-6061", "CN", "CN", 0.70, "N"),
                ("SUP-31", "MAT-A572", "KR", "KR", 0.74, "N"), ("SUP-30", "MAT-4140", "US", "US", 1.10, "N"),
                ("SUP-04", "MAT-A572", "KR", "US", 0.72, "N"), ("SUP-38", "MAT-TI64", "CN", "CN", 1.05, "N")], 3)))
            slot("S2", "Pintle pin", 1, self.sm_part(pid, "S2", R(700, 1100), R(450, 700), "machined_part", self.pick([
                ("SUP-30", "MAT-4340", "US", "US", 1.00, "N"), ("SUP-31", "MAT-4340", "KR", "KR", 0.74, "N"),
                ("SUP-31", "MAT-1541", "KR", "KR", 0.66, "N"), ("SUP-32", "MAT-1340", "IN", "IN", 0.62, "N")], 3)))
            slot("S3", "Spring", 2, self.sm_part(pid, "S3", R(150, 260), R(60, 110), "machined_part", [
                ("SUP-07", "MAT-5160", "US", "US", 1.00, "N"), ("SUP-36", "MAT-5160", "JP", "JP", 0.82, "N"),
                ("SUP-10", "MAT-5160", "CN", "CN", 0.60, "N")]))
            slot("S4", "Sight bracket and electronics module", 1, self.electronic(pid, "S4", R(6000, 9000), sm_g=R(100, 250)))
            slot("S5", "Bolt set", 1, self.fasteners(pid, "S5", R(250, 500), R(80, 140), "MAT-4140"))
            slot("S6", "Traverse lock assembly", 1, self.lock_offers(pid, "S6"))
            asm = R(1800, 3200); qty = R(40, 160)
        elif fam == "blower":
            desc = self.rng.choice(["Ventilation blower assembly, 24 V", "NBC filter blower assembly", "Crew compartment fan assembly"])
            slot("S1", "Drive motor assembly", 1, self.motor_offers(pid, "S1"))
            slot("S2", "Blower housing, cast stainless", 1, self.sm_part(pid, "S2", R(3500, 5200), R(3200, 4600), "casting", [
                ("SUP-30", "MAT-304", "US", "US", 1.00, "N"), ("SUP-31", "MAT-304", "KR", "KR", 0.76, "N"),
                ("SUP-10", "MAT-304", "CN", "CN", 0.64, "Y")]))
            slot("S4", "Motor controller board", 1, self.electronic(pid, "S4", R(2400, 3800), broker=self.rng.random() < 0.5, sm_g=R(20, 60)))
            slot("S5", "Fan impeller, glass-filled nylon", 1, self.generic(pid, "S5", R(500, 900), k=3))
            asm = R(1500, 2800); qty = R(60, 240)
        elif fam == "shelving":
            desc = self.rng.choice(["Steel shelving unit, 5 shelf, 36 x 18 x 72 in", "Steel shelving unit, 6 shelf, 48 x 24 x 84 in",
                                    "Boltless rivet shelving, 4 shelf, 60 x 24 x 72 in"])
            nsh = R(4, 6)
            slot("S1", "Upright post, roll-formed steel", 4, self.steel_sheet(pid, "S1", R(1500, 2600), R(2500, 3500), inhouse=self.rng.random() < 0.4))
            slot("S2", "Shelf panel, cold-rolled steel sheet", nsh, self.steel_sheet(pid, "S2", R(1900, 3100), R(4000, 6000)))
            slot("S3", "Shelf clip and bolt set, per shelf", nsh, self.fasteners(pid, "S3", R(220, 420), R(60, 120)))
            slot("S4", "Leveling foot, molded plastic", 4, self.generic(pid, "S4", R(60, 140)))
            slot("S5", "Powder coat finish material", 1, self.generic(pid, "S5", R(500, 900)))
            asm = R(2200, 4200); qty = R(60, 300)
        elif fam == "cabinet":
            desc = self.rng.choice(["Steel storage cabinet, 2 door, 36 x 18 x 72 in", "Flammable liquid safety cabinet, 30 gal",
                                    "Steel wardrobe cabinet, 36 x 24 x 78 in"])
            slot("S1", "Cabinet body, cold-rolled steel sheet", 1, self.steel_sheet(pid, "S1", R(9000, 14000), R(18000, 26000), inhouse=self.rng.random() < 0.5))
            slot("S2", "Door panel, cold-rolled steel sheet", 2, self.steel_sheet(pid, "S2", R(2600, 3800), R(5000, 7000)))
            slot("S3", "Hinge, latch and bolt hardware kit", 1, self.fasteners(pid, "S3", R(1200, 2200), R(400, 700)))
            slot("S4", "Locking handle assembly", 1, self.generic(pid, "S4", R(900, 1500)))
            slot("S5", "Powder coat finish material", 1, self.generic(pid, "S5", R(900, 1500)))
            asm = R(4500, 7500); qty = R(40, 200)
        elif fam == "handtruck":
            desc = self.rng.choice(["Convertible hand truck, 600 lb", "Appliance hand truck, 800 lb", "Platform truck, 1200 lb, 24 x 48 in"])
            slot("S1", "Frame, welded steel tube", 1, self.steel_sheet(pid, "S1", R(3600, 5400), R(9000, 13000), coated=False, inhouse=self.rng.random() < 0.5))
            slot("S2", "Pneumatic wheel, 10 in", 2, self.generic(pid, "S2", R(1700, 2700), k=3))
            slot("S3", "Axle, steel bar", 1, self.steel_sheet(pid, "S3", R(500, 950), R(1200, 1800), k=2, coated=False))
            slot("S4", "Handle grip set", 1, self.generic(pid, "S4", R(250, 450)))
            slot("S5", "Nose plate, steel", 1, self.steel_sheet(pid, "S5", R(800, 1400), R(2000, 3000), k=2))
            slot("S6", "Hardware kit", 1, self.fasteners(pid, "S6", R(150, 300), R(60, 110)))
            asm = R(1500, 2800); qty = R(80, 400)
        elif fam == "brush":
            desc = self.rng.choice(["Push broom, 24 in, stiff fill", "Push broom, 36 in, medium fill", "Industrial floor brush, 18 in"])
            slot("S1", "Brush block, hardwood", 1, self.generic(pid, "S1", R(300, 600), us="SUP-20"))
            fill = R(700, 1300)
            slot("S2", "Brush fill", 1, [
                self.offer(pid, "S2", "SUP-18", "CN", int(fill * self.u(0.55, 0.70)), mclass="hog bristles", cert=self.rng.random() < 0.3),
                self.offer(pid, "S2", "SUP-09", "US", int(fill * self.u(0.95, 1.10)), mclass="polypropylene filament"),
                self.offer(pid, "S2", "SUP-11", "VN", int(fill * self.u(0.60, 0.75)), mclass="polypropylene filament")])
            slot("S3", "Handle, ash wood, 60 in", 1, self.generic(pid, "S3", R(400, 700), us="SUP-20"))
            slot("S4", "Handle brace, steel", 1, self.steel_sheet(pid, "S4", R(150, 260), R(250, 400), k=2))
            asm = R(300, 700); qty = R(150, 600)
        elif fam == "mat":
            desc = self.rng.choice(["Anti-fatigue floor mat, 3 x 5 ft", "Drainage floor mat, 3 x 10 ft", "Entrance scraper mat, 4 x 6 ft"])
            rub = R(2400, 4200)
            slot("S1", "Rubber compound", 1, [
                self.offer(pid, "S1", "SUP-17", "LK", int(rub * self.u(0.55, 0.70)), mclass="natural rubber, crude", cert=self.rng.random() < 0.4),
                self.offer(pid, "S1", "SUP-21", "US", int(rub * self.u(0.95, 1.10)), mclass="synthetic rubber (SBR)"),
                self.offer(pid, "S1", "SUP-11", "VN", int(rub * self.u(0.60, 0.78)), mclass="synthetic rubber (SBR)", cert=self.rng.random() < 0.4)])
            slot("S2", "Foam cushion core", 1, self.generic(pid, "S2", R(800, 1500), k=3, cert_p=0.4))
            slot("S3", "Beveled edge strip", 4, self.generic(pid, "S3", R(80, 160)))
            slot("S4", "Bonding adhesive", 1, self.generic(pid, "S4", R(200, 400), cert_p=0.4))
            asm = R(700, 1400); qty = R(100, 500)
        elif fam == "timer":
            desc = self.rng.choice(["Programmable process timer, panel mount", "Digital cycle counter, DIN rail", "HVAC time clock, 7 day"])
            slot("S1", "Printed circuit board assembly", 1, self.electronic(pid, "S1", R(2400, 4200)))
            xt = R(150, 320)
            slot("S2", "Quartz crystal, 32.768 kHz", 1, [
                self.offer(pid, "S2", "SUP-16", "JP", int(xt * self.u(0.45, 0.60)), "electronic", mclass="quartz crystals"),
                self.offer(pid, "S2", "SUP-10", "CN", int(xt * self.u(0.40, 0.55)), "electronic", mclass="quartz crystals"),
                self.offer(pid, "S2", "SUP-13", "US", int(xt * self.u(0.95, 1.10)), "electronic", mclass="quartz crystals")])
            slot("S3", "Enclosure, molded polycarbonate", 1, self.generic(pid, "S3", R(600, 1000)))
            slot("S4", "LCD display module", 1, self.electronic(pid, "S4", R(900, 1500), broker=self.rng.random() < 0.5))
            slot("S5", "Output relay", 2, self.generic(pid, "S5", R(300, 600), k=3, cert_p=0.4))
            slot("S6", "Wiring harness", 1, self.generic(pid, "S6", R(300, 600)))
            asm = R(1200, 2400); qty = R(80, 400)
        elif fam == "led":
            desc = self.rng.choice(["LED high-bay fixture, 150 W", "LED troffer, 2 x 4 ft, 40 W", "LED wall pack, 80 W"])
            slot("S1", "LED driver", 1, self.electronic(pid, "S1", R(2200, 3600)))
            slot("S2", "LED board", 1, self.electronic(pid, "S2", R(1800, 3000), broker=False))
            hs = R(1400, 2400)
            slot("S3", "Heat sink, extruded aluminum", 1, [
                self.inhouse(pid, "S3", int(hs * self.u(0.80, 0.95))),
                self.offer(pid, "S3", "SUP-12", "MX", int(hs * self.u(0.70, 0.85)), cert=self.rng.random() < 0.3),
                self.offer(pid, "S3", "SUP-28", "DE", int(hs * self.u(0.72, 0.88)))])
            slot("S4", "Lens, polycarbonate", 1, self.generic(pid, "S4", R(500, 900)))
            slot("S5", "Mounting bracket, steel", 1, self.steel_sheet(pid, "S5", R(300, 600), R(500, 900), k=2))
            asm = R(1000, 2000); qty = R(100, 500)
        elif fam == "charger":
            desc = self.rng.choice(["Forklift battery charger, 48 V, 85 A", "Battery charger, 24 V, 40 A", "Floor scrubber battery charger, 36 V"])
            slot("S1", "Power transformer", 1, self.generic(pid, "S1", R(6000, 9500), k=3, cert_p=0.3))
            slot("S2", "Control board", 1, self.electronic(pid, "S2", R(4000, 6500)))
            slot("S3", "Cabinet, aluminum sheet", 1, self.generic(pid, "S3", R(2500, 3800)))
            slot("S4", "Output cable set", 1, self.generic(pid, "S4", R(900, 1500)))
            slot("S5", "Cooling fan", 1, self.generic(pid, "S5", R(400, 800)))
            asm = R(2500, 4500); qty = R(30, 150)
        elif fam == "cots_kit":
            cots = "Y"
            desc = self.rng.choice(["First aid kit, 50 person, ANSI Class A", "Spill kit, universal, 20 gal", "Emergency response kit, 25 person"])
            slot("S1", "Case, molded polypropylene", 1, self.generic(pid, "S1", R(900, 1600), k=3))
            slot("S2", "Contents set", 1, self.generic(pid, "S2", R(2500, 4500), k=3))
            slot("S3", "Wall mount bracket, steel", 1, self.steel_sheet(pid, "S3", R(200, 400), R(300, 500), k=2))
            slot("S4", "Labels and instructions", 1, self.generic(pid, "S4", R(100, 250)))
            asm = R(500, 1100); qty = R(100, 500)
        elif fam == "cots_steel":
            cots = "Y"
            desc = self.rng.choice(["Steel tool chest, 26 in, 5 drawer", "Steel roller cabinet, 41 in, 10 drawer", "Steel workbench, 72 in"])
            slot("S1", "Body, cold-rolled steel sheet", 1, self.steel_sheet(pid, "S1", R(7000, 11000), R(15000, 22000)))
            slot("S2", "Drawer, steel sheet", R(5, 10), self.steel_sheet(pid, "S2", R(900, 1500), R(1800, 2600)))
            slot("S3", "Drawer slide hardware", 1, self.fasteners(pid, "S3", R(800, 1500), R(300, 500)))
            slot("S4", "Caster, polyurethane", 4, self.generic(pid, "S4", R(300, 600)))
            slot("S5", "Drawer liner set", 1, self.generic(pid, "S5", R(300, 600)))
            asm = R(3000, 5000); qty = R(40, 200)
        elif fam == "slides":
            desc = self.rng.choice(["Prepared microscope slide set, histology, 50 slides", "Blank slide kit with cover glass, 144 slides"])
            slot("S1", "Glass microscope slides", 1, [
                self.offer(pid, "S1", "SUP-19", "DE", R(900, 1300), mclass="glass microscope slides"),
                self.offer(pid, "S1", "SUP-10", "CN", R(700, 1000), mclass="glass microscope slides"),
                self.offer(pid, "S1", "SUP-26", "US", R(1300, 1800), mclass="glass microscope slides")])
            slot("S2", "Cover glass", 1, [
                self.offer(pid, "S2", "SUP-10", "CN", R(450, 700), mclass="cover glass, microscope slide"),
                self.offer(pid, "S2", "SUP-26", "US", R(800, 1200), mclass="cover glass, microscope slide")])
            slot("S3", "Staining reagent set", 1, self.generic(pid, "S3", R(800, 1400)))
            slot("S4", "Slide storage box", 1, self.generic(pid, "S4", R(300, 600)))
            asm = R(1500, 3000); qty = R(50, 250)
        else:
            raise ValueError(fam)
        prod = dict(product_id=pid, description=desc, item_number="", next_higher_assembly=use, quantity=str(qty),
                    cots_item=cots, assembly_cost_cents=str(asm))
        return dict(prod=prod, bom=bom, offers=offers, imports=[], fam=fam)

    def add_import(self, part, eval_cents, sup=None, qc_share=None, steel_share=None, bad_share=None, nis_share=None):
        pid = part["prod"]["product_id"]
        sup = sup or self.rng.choice(IMPORTERS)
        country = COUNTRY[sup]
        frt = int(eval_cents * self.u(0.03, 0.06))
        duty = int(eval_cents * self.rng.choice([0.0, 0.025, 0.035, 0.05]))
        price = eval_cents - frt - duty
        T = int(eval_cents * self.u(0.45, 0.65))
        if qc_share is None:
            qc_share = self.u(0.55, 0.95) if country in bacore.QC else self.u(0.0, 0.3)
        fam = part["fam"]
        st = steel_share if steel_share is not None else (self.u(0.55, 0.8) if fam in ("battery_box", "hinge", "mount", "shelving", "cabinet", "handtruck", "cots_steel") else self.u(0.0, 0.2))
        IS = int(T * st)
        if nis_share is None:
            nis_share = self.u(0.0, 0.06) if country in bacore.QC else self.u(0.3, 1.0)
        nis = int(IS * nis_share)
        smt = self.r(3000, 12000) if fam in ("battery_box", "hinge", "mount", "blower") else 0
        if bad_share is None:
            bad_share = 0.0 if country in bacore.QC or self.rng.random() < 0.3 else self.u(0.05, 0.8)
        part["imports"].append(dict(offer_id=f"tmpF{self.r(1, 10**9)}", product_id=pid, supplier_id=sup,
                                    country_of_manufacture=country, unit_price_cents=str(price), freight_cents=str(frt),
                                    duty_cents=str(duty), cost_of_components_cents=str(T),
                                    us_qc_component_cost_cents=str(int(T * qc_share)), iron_steel_cost_cents=str(IS),
                                    non_us_qc_iron_steel_cost_cents=str(nis), specialty_metal_g=str(smt),
                                    noncompliant_specialty_metal_g=str(int(smt * bad_share))))


# ---------------- product-level checks ----------------
# The shipped instance was planted while the rules still read every iron alloy as steel. Planting keeps that
# reading so the seed reproduces the shipped products; the answers (expected.json, budget) and calibrate.py
# use the corrected rules, and every planted reading is re-checked there against the shipped instance.
PLANT_FLAGS = ("sm_ignore_carbon",)
QUAL = set()
PARAMS = {}
MATS = {m[0]: dict(material_id=m[0], name=m[1], base_metal=m[2], **{f"max_{e}": m[3].get(e, "0.00") for e in ELEMENTS})
        for m in MATERIALS}


def mini_inst(part):
    pid = part["prod"]["product_id"]
    by_slot = {}
    for o in part["offers"]:
        by_slot.setdefault((pid, o["slot"]), []).append(o)
    subs = {o["offer_id"]: o["_inner"] for o in part["offers"] if "_inner" in o}
    return dict(params=PARAMS, subs=subs, suppliers={}, products={pid: part["prod"]}, materials=MATS, bom={pid: part["bom"]},
                offers={}, by_slot=by_slot, imports={},
                imports_by_product={pid: part["imports"]} if part["imports"] else {})


def bkey(b):
    return ("imp", b["import_offer"]) if b["build"] == "import" else tuple(sorted(b["offers"].items()))


def view(part, flags=(), qual=None):
    qual = QUAL if qual is None else qual
    pid = part["prod"]["product_id"]
    R = bacore.Rules(mini_inst(part), tuple(flags) + PLANT_FLAGS)
    blds = R.builds(pid)
    st, info = R.admissibility(pid, blds)
    al = [b for b in blds if bacore.allowed(st, b)]
    alq = [b for b in al if qual is ALL or b["suppliers"] <= qual]
    return dict(status=st, info=info, builds=blds, allowed={bkey(b) for b in al},
                best=min(alq, key=lambda b: b["unit_outlay"]) if alq else None)


ALL = object()


def _effect(part, flag, qual):
    t, s = view(part, qual=qual), view(part, (flag,), qual=qual)
    if t["best"] is None:
        return False
    if s["best"] is None:
        return True
    return bkey(s["best"]) not in t["allowed"] or s["best"]["unit_outlay"] > t["best"]["unit_outlay"]


def effect(part, flag):
    """True only if the misreading changes this product's answer both with the current approved
    vendors and with every vendor qualified."""
    if flag == "far_fallback":
        return _effect(part, flag, QUAL) or _effect(part, flag, ALL)
    return _effect(part, flag, QUAL) and _effect(part, flag, ALL)


def sane(part):
    t = view(part)
    acc = [b for b in t["builds"] if b["sm_ok"]]
    if not any(b["domestic"] for b in acc) or t["best"] is None:
        return False
    L = min(b["unit_eval"] for b in acc)
    if len([b for b in acc if b["unit_eval"] == L]) != 1:
        return False
    outs = sorted(b["unit_outlay"] for b in t["builds"] if bkey(b) in t["allowed"])
    return len(outs) < 2 or outs[0] != outs[1]


def lowest_domestic(part):
    t = view(part)
    return min((b for b in t["builds"] if b["domestic"] and b["sm_ok"]), key=lambda b: b["unit_eval"])


def plant(g, fam, pid, flag, tweak=None, use=None, tries=20000):
    for _ in range(tries):
        part = g.family(fam, pid, use=use(g) if callable(use) else use)
        if tweak and not tweak(g, part):
            continue
        if sane(part) and effect(part, flag) and not effect(part, "far_fallback"):
            return part
    raise RuntimeError(f"could not plant {flag} in {fam}")


def tw_import(lo, hi, **kw):
    def f(g, part):
        try:
            D = lowest_domestic(part)["unit_eval"]
        except ValueError:
            return False
        g.add_import(part, int(D / g.u(lo, hi)), **{k: (v(g) if callable(v) else v) for k, v in kw.items()})
        return True
    return f


def tw_two_imports(g, part):
    """Rule (D): cheap non-exempt foreign import, and an exempt QC import between it and the lowest domestic."""
    try:
        D = lowest_domestic(part)["unit_eval"]
    except ValueError:
        return False
    g.add_import(part, int(D / g.u(1.25, 1.45)), sup=g.rng.choice(["SUP-22", "SUP-24", "SUP-25"]), bad_share=0.0)
    g.add_import(part, int(D / g.u(1.01, 1.08)), sup=g.rng.choice(["SUP-42", "SUP-43", "SUP-45"]), qc_share=g.u(0.8, 0.95),
                 steel_share=0.1)
    return True


def tw_eval_tie(g, part):
    try:
        D = lowest_domestic(part)["unit_eval"]
    except ValueError:
        return False
    if D % 3:
        part["prod"]["assembly_cost_cents"] = str(int(part["prod"]["assembly_cost_cents"]) + (3 - D % 3))
        D = lowest_domestic(part)["unit_eval"]
        if D % 3:
            return False
    L = D * 2 // 3
    g.add_import(part, L, sup=g.rng.choice(["SUP-22", "SUP-24", "SUP-25"]), bad_share=0.0)
    imp = part["imports"][-1]
    tot = int(imp["unit_price_cents"]) + int(imp["freight_cents"]) + int(imp["duty_cents"])
    imp["unit_price_cents"] = str(int(imp["unit_price_cents"]) + L - tot)
    return True


def tw_exact_ratio(num, den):
    def f(g, part):
        v = view(part)
        us = sorted((b for b in v["builds"] if b["build"] == "us"), key=lambda x: x["unit_outlay"])
        qty = {r["slot"]: int(r["qty_per_unit"]) for r in part["bom"]}
        for b in us:
            T, Dm = b["cost_of_components"], b["domestic_component_cost"]
            if not (0.60 * T < Dm < num * T / den):
                continue
            for o in [o for o in part["offers"] if b["offers"].get(o["slot"]) == o["offer_id"]]:
                if o["component_origin"] != "US" or qty[o["slot"]] != 1 or o["supply_type"] != "purchased" or o["iron_steel_cost_cents"] != "0":
                    continue
                x0 = int(o["unit_price_cents"]) + int(o["freight_cents"])
                top = num * (T - x0) - den * (Dm - x0)
                if top <= 0 or top % (den - num):
                    continue
                price = top // (den - num) - int(o["freight_cents"])
                if price <= 0 or abs(price - int(o["unit_price_cents"])) > 0.35 * int(o["unit_price_cents"]):
                    continue
                o["unit_price_cents"] = str(price)
                return True
        return False
    return f


def tw_sm_exact2(g, part):
    """Make a cheap build's noncompliant specialty metal exactly 2% of its total weight, by resizing a
    compliant specialty-metal part in that build."""
    v = view(part)
    R = bacore.Rules(mini_inst(part), PLANT_FLAGS)
    qty = {r["slot"]: int(r["qty_per_unit"]) for r in part["bom"]}
    for b in sorted((b for b in v["builds"] if b["build"] == "us" and b["sm_bad"]), key=lambda x: x["unit_outlay"]):
        T, B = b["sm_total"], b["sm_bad"]
        if not (0.01 * T < B < 0.04 * T):
            continue
        for o in [o for o in part["offers"] if b["offers"].get(o["slot"]) == o["offer_id"]]:
            w, bad, _ = R.sm_piece(o, 0)
            q = qty[o["slot"]]
            if not w or bad:
                continue
            need = 50 * B - (T - q * w)
            if need <= 0 or need % q:
                continue
            y = need // q
            if abs(y - w) > 0.3 * w:
                continue
            o["metal_g_per_piece"] = str(y)
            return True
    return False


def tw_pred_tie(g, part):
    v = view(part)
    qty = {r["slot"]: int(r["qty_per_unit"]) for r in part["bom"]}
    for b in sorted((b for b in v["builds"] if b["build"] == "us"), key=lambda x: x["unit_outlay"]):
        T, IS = b["cost_of_components"], b["iron_steel_cost"]
        if not (0.40 * T < IS < 0.60 * T):
            continue
        for o in [o for o in part["offers"] if b["offers"].get(o["slot"]) == o["offer_id"]]:
            if o["iron_steel_cost_cents"] != "0" or o["supply_type"] != "purchased":
                continue
            q = qty[o["slot"]]
            fd = int(o["freight_cents"]) + int(o["duty_cents"])
            need = 2 * IS - (T - q * (int(o["unit_price_cents"]) + fd))
            if need <= 0 or need % q:
                continue
            price = need // q - fd
            if price <= 0 or abs(price - int(o["unit_price_cents"])) > 0.35 * int(o["unit_price_cents"]):
                continue
            o["unit_price_cents"] = str(price)
            return True
    return False


def chain(*fs):
    return lambda g, part: all(fn(g, part) for fn in fs)


def veh(g):
    return g.rng.choice(VEHICLES)


def wpn(g):
    return g.rng.choice(WEAPONS)


def look(g):
    g.rng.choice(LOOKALIKE)        # keeps the draw sequence of earlier versions
    return FACILITY


DOMREQ = tw_import(1.05, 1.40)
FORALLOW = tw_import(1.55, 2.20, sup=lambda g: g.rng.choice(["SUP-22", "SUP-23", "SUP-24", "SUP-25"]), bad_share=0.0)
EITHER = lambda g, part: (DOMREQ if g.rng.random() < 0.5 else FORALLOW)(g, part)
QCIMP = tw_import(1.05, 1.30, sup=lambda g: g.rng.choice(["SUP-42", "SUP-43", "SUP-45"]),
                  qc_share=lambda g: g.u(0.8, 0.95), steel_share=0.05, bad_share=0.0)
PLAN = [
    # FAR-level readings on facility products
    ("timer", "nonstrict", chain(tw_exact_ratio(3, 4), DOMREQ), None),
    ("cabinet", "nonstrict", chain(tw_pred_tie, DOMREQ), None),
    ("timer", "stale_threshold", DOMREQ, None),
    ("led", "unknown_domestic", DOMREQ, None),
    ("timer", "cert_no_duty", DOMREQ, None),
    ("brush", "ignore_list", DOMREQ, None),
    ("mat", "ignore_list", DOMREQ, None),
    ("timer", "ignore_notice", DOMREQ, None),
    ("cots_kit", "no_cots_waiver", DOMREQ, None),
    ("cots_steel", "cots_waives_steel", DOMREQ, None),
    ("shelving", "count_fasteners", DOMREQ, None),
    ("cabinet", "profit_in_cost", DOMREQ, None),
    ("timer", "assembly_in_cost", DOMREQ, None),
    ("led", "tie_foreign", tw_eval_tie, None),
    # DFARS Buy American readings
    ("led", "qc_not_domestic", DOMREQ, None),
    ("slides", "qc_not_domestic", DOMREQ, None),
    ("shelving", "korea_qc", DOMREQ, None),
    ("cabinet", "korea_qc", DOMREQ, None),
    ("charger", "factor30", tw_import(1.32, 1.48, sup=lambda g: g.rng.choice(["SUP-22", "SUP-24", "SUP-25"]), bad_share=0.0), None),
    ("led", "factor30", tw_import(1.32, 1.48, sup=lambda g: g.rng.choice(["SUP-22", "SUP-24", "SUP-25"]), bad_share=0.0), None),
    ("charger", "qc_considered", QCIMP, None),
    ("led", "qc_considered", QCIMP, None),
    # specialty metals readings
    ("battery_box", "sm_ignore", DOMREQ, veh),
    ("hinge", "sm_ignore", DOMREQ, veh),
    ("battery_box", "sm_everywhere", DOMREQ, look),
    ("hinge", "sm_everywhere", DOMREQ, look),
    ("mount", "sm_nonstrict_comp", DOMREQ, wpn),
    ("mount", "sm_hsla", EITHER, wpn),
    ("battery_box", "sm_mn_ignore", EITHER, veh),
    ("battery_box", "sm_all_processes", EITHER, veh),
    ("blower", "sm_no_qc_mfg", EITHER, veh),
    ("blower", "sm_no_qc_mfg", DOMREQ, veh),
    ("hinge", "sm_cost_basis", DOMREQ, veh),
    ("blower", "sm_magnet_2pct", DOMREQ, veh),
    ("battery_box", "sm_cots_all", DOMREQ, veh),
    ("hinge", "sm_no_fastener_cert", DOMREQ, veh),
    ("hinge", "sm_strict_2pct", chain(tw_sm_exact2, DOMREQ), veh),
    ("mount", "sm_no_elim", tw_import(1.3, 1.9, sup=lambda g: g.rng.choice(["SUP-22", "SUP-24", "SUP-46"]),
                                      bad_share=lambda g: g.u(0.3, 0.8)), wpn),
    ("battery_box", "sm_electronic_restricted", DOMREQ, veh),
    ("charger", "always_domestic", FORALLOW, None),
    ("led", "always_domestic", FORALLOW, None),
    ("timer", "always_domestic", FORALLOW, None),
    # sub-assemblies
    ("blower", "sm_top_level_only", DOMREQ, veh),
    ("mount", "sm_top_level_only", DOMREQ, wpn),
    ("blower", "sm_cots_assembly_magnet", DOMREQ, veh),
    ("mount", "sm_cots_assembly_ignored", DOMREQ, wpn),
    ("blower", "ba_rollup", DOMREQ, veh),
    ("blower", "ba_rollup", DOMREQ, veh),
]
FILLER = [("blower", "look"), ("hinge", "veh")]


def build(seed):
    g = Gen(seed)
    PARAMS.clear()
    PARAMS.update({
        "solicitation": "SPE7L3-27-R-0118, tactical vehicle and weapon spares plus facility supplies, total small business set-aside",
        "contracting_agency": "Defense Logistics Agency, Land and Maritime",
        "buy_american_clause": "DFARS 252.225-7001 Buy American and Balance of Payments Program, Basic (FEB 2024)",
        "specialty_metals_clause": "DFARS 252.225-7009 Restriction on Acquisition of Certain Articles Containing Specialty Metals (JAN 2023)",
        "small_business_set_aside": True,
        "trade_agreements_apply": False,
        "award_basis": "lowest evaluated price",
        "offeror_size": "small",
        "delivery_calendar_year": 2029,
        "evaluation_date": "2027-02-15",
        "nonavailable_articles_available_domestically": ["Quartz crystals"],
        "public_interest_determinations": [],
        "specialty_metal_nonavailability_determinations": [],
        "qualification_budget_cents": 0,
    })
    QUAL.clear()
    fees = {}
    for sid, _, _ in SUPPLIERS:
        if sid in NEW_VENDORS:
            fees[sid] = g.r(3, 15) * 10000
        else:
            QUAL.add(sid)
    specs = [(f, fl, tw, use) for f, fl, tw, use in PLAN] + [(f, None, None, use) for f, use in FILLER]
    g.rng.shuffle(specs)
    parts = []
    usefn = {"look": look, "wpn": wpn, "veh": veh, None: None}
    for i, (fam, flag, tw, use) in enumerate(specs):
        pid = f"P{i + 1:02d}"
        if flag:
            part = plant(g, fam, pid, flag, tw, use=use)
        else:
            for _ in range(3000):
                part = g.family(fam, pid, use=usefn[use](g) if use in usefn and usefn[use] else None)
                if g.rng.random() < 0.7:
                    tw_import(0.9, 1.8)(g, part)
                if sane(part) and not effect(part, "far_fallback"):
                    break
            else:
                raise RuntimeError(f"no sane filler {fam}")
        part["flag"] = flag
        pre = {"shelving": "SHV", "cabinet": "CAB", "handtruck": "HTK", "brush": "BRM", "mat": "MAT", "timer": "TMR",
               "led": "LED", "charger": "CHG", "cots_kit": "KIT", "cots_steel": "TCH", "slides": "SLD",
               "battery_box": "BBX", "hinge": "HNG", "mount": "MNT", "blower": "BLW"}[fam]
        while True:
            item = f"{pre}-{g.r(1000, 9999)}"
            if item not in {p["prod"]["item_number"] for p in parts}:
                break
        part["prod"]["item_number"] = item
        parts.append(part)
    n = m = 0
    for part in parts:
        for o in part["offers"]:
            n += 1
            o["offer_id"] = f"C{n:04d}"
        for imp in part["imports"]:
            m += 1
            imp["offer_id"] = f"F{m:03d}"
    add_sight_windows(seed, parts, n)
    used = {o["supplier_id"] for p in parts for o in p["offers"]} | {x["supplier_id"] for p in parts for x in p["imports"]}
    suppliers = [dict(supplier_id=sid, name=name, country=c, qualified="Y" if sid in QUAL else "N",
                      qualification_fee_cents=str(fees.get(sid, 0))) for sid, name, c in SUPPLIERS if sid in used]
    return g, dict(PARAMS), parts, suppliers


def add_sight_windows(seed, parts, n):
    """Glass-sealed sight window on every mount (iron-nickel alloy frame, below the steel carbon range).
    Added after every earlier draw and numbered after the existing offers, so the rest of the instance
    is exactly what earlier versions generated (own random stream)."""
    g = Gen(seed * 1000 + 7)
    for part in parts:
        if not any(r["part_description"] == "Pintle pin" for r in part["bom"]):
            continue
        pid = part["prod"]["product_id"]
        base, grams = g.r(700, 1100), g.r(60, 95)
        part["bom"].append(dict(product_id=pid, slot="S7", part_description="Sight window, glass-sealed frame", qty_per_unit="1"))
        offs = [g.offer(pid, "S7", sup, None, int(base * mult * g.u(0.97, 1.03)), "fabricated_part",
                        duty_rate=0.0 if COUNTRY[sup] == "US" else None, mat="MAT-FNC", grams=grams, melt=melt,
                        ore="AU" if melt != "US" else "US")
                for sup, melt, mult in (("SUP-26", "US", 1.00), ("SUP-19", "DE", 0.84), ("SUP-10", "CN", 0.58))]
        for o in offs:
            n += 1
            o["offer_id"] = f"C{n:04d}"
        part["offers"].extend(offs)


def write(task_dir, params, parts, suppliers):
    for sub in ("environment/data", "tests/data"):
        d = os.path.join(task_dir, sub)
        os.makedirs(d, exist_ok=True)
        for old in os.listdir(d):
            os.remove(os.path.join(d, old))
        json.dump(params, open(os.path.join(d, "params.json"), "w"), indent=2)

        def wcsv(name, rows, cols):
            with open(os.path.join(d, name), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
                w.writeheader()
                for r in rows:
                    w.writerow({c: r[c] for c in cols})
        wcsv("suppliers.csv", suppliers, ["supplier_id", "name", "country", "qualified", "qualification_fee_cents"])
        wcsv("products.csv", [p["prod"] for p in parts], ["product_id", "description", "item_number", "next_higher_assembly",
                                                          "quantity", "cots_item", "assembly_cost_cents"])
        wcsv("bom.csv", [r for p in parts for r in p["bom"]], ["product_id", "slot", "part_description", "qty_per_unit"])
        wcsv("component_offers.csv", [o for p in parts for o in p["offers"]], OCOLS)
        wcsv("finished_imports.csv", [x for p in parts for x in p["imports"]],
             ["offer_id", "product_id", "supplier_id", "country_of_manufacture", "unit_price_cents", "freight_cents",
              "duty_cents", "cost_of_components_cents", "us_qc_component_cost_cents", "iron_steel_cost_cents",
              "non_us_qc_iron_steel_cost_cents", "specialty_metal_g", "noncompliant_specialty_metal_g"])
        wcsv("subassembly_contents.csv",
             [dict(assembly_offer_id=o["offer_id"], **r) for p in parts for o in p["offers"] for r in o.get("_inner", [])],
             ["assembly_offer_id", "item_no", "description", "qty", "item_origin", "part_form", "component_cots",
              "metal_material", "metal_g_per_piece", "metal_melt_country", "metal_rolling_country",
              "metal_coating_country", "iron_steel_cost_cents", "unit_cost_cents"])
        wcsv("materials.csv", list(MATS.values()), ["material_id", "name", "base_metal"] + [f"max_{e}" for e in ELEMENTS])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SECRET_SEED)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "tasks", "buy-american-sourcing"))
    ap.add_argument("--budget-frac", type=float, default=0.6)
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
    params["qualification_budget_cents"] = -(-budget // 10000) * 10000
    write(a.out, params, parts, suppliers)
    inst = bacore.load(tmp)
    sol = bacore.optimize(inst)
    out = bacore.to_output(inst, sol)
    json.dump(dict(total_outlay_cents=out["total_outlay_cents"],
                   admissibility={l["product_id"]: l["admissibility"] for l in out["lines"]},
                   unbudgeted_total_outlay_cents=free["total_outlay"], unbudgeted_spend_cents=free["qualification_spend"]),
              open(os.path.join(a.out, "tests", "expected.json"), "w"), indent=2)
    if not a.quiet:
        from collections import Counter
        print("min feasible spend", need, "budget", params["qualification_budget_cents"], "free", free["total_outlay"])
        print("optimum", sol["total_outlay"], "spend", sol["qualification_spend"], "new", sol["new_qualifications"])
        print(Counter(sol["status"].values()))
        print("restricted lines:", sum(1 for l in out["lines"] if l["specialty_metals_restricted"]))


if __name__ == "__main__":
    main()
