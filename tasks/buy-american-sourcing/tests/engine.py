"""Independent verifier engine for the buy-american-sourcing task (DoD version).

Reads only /tests/data. Applies DFARS 252.225-7001 (Basic, FEB 2024), DFARS 252.225-7009 (JAN 2023)
with 225.7003-1/-2/-3, DFARS 225.502(c)(ii) and 225.106, DFARS 225.872-1 and 225.872-3(a), FAR 25.104 and FAR
25.502(d)(1) in exact integer arithmetic by enumerating every build of every product, then finds the
minimum total outlay with a selection MILP (HiGHS via scipy). Written independently of the reference
solution, which uses CP-SAT.
"""
import csv
import itertools
import json
import os
from fractions import Fraction

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

DATA = os.environ.get("VERIFIER_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

QUALIFYING = frozenset("AU AT BE CA CZ DK EG EE FI FR DE GR IL IT JP LV LT LU NL NO PL PT SI ES SE CH TR GB".split())
CASE_BY_CASE = frozenset({"AT"})                      # 225.872-1(b)
NONAVAILABLE = {                                      # FAR 25.104(a) entries used by material_class
    "hog bristles": "Hog bristles for brushes",
    "natural rubber, crude": "Rubber, crude and latex (natural)",
    "quartz crystals": "Quartz crystals",
    "cover glass, microscope slide": "Cover glass, microscope slide",
}
RESTRICTED_USE = {                                    # 225.7003-2(a)(1) and the automotive item definition
    "M1083A1 FMTV 5-ton cargo truck": True,
    "M1151A1 HMMWV armament carrier": True,
    "M1126 Stryker infantry carrier vehicle": True,
    "M2A1 .50 caliber machine gun (crew-served weapon)": True,
    "M240B 7.62 mm machine gun (crew-served weapon)": True,
    "Warehouse and facility use": False,
}
STEEL_LIMITS = {"mn": Fraction("1.65"), "si": Fraction("0.60"), "cu": Fraction("0.60")}
STEEL_ELEMENTS = ("al", "cr", "co", "mo", "ni", "nb", "ti", "w", "v")
NOT_COTS_EXCEPTED = frozenset({"mill_product", "forging", "casting", "magnet", "fastener"})

TRACKS = ("domestic_component_test", "domestic_iron_steel", "domestic_cots", "foreign")
STATUSES = ("domestic_required", "foreign_allowed")


def _rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _i(v):
    return int(v) if v not in ("", None) else 0


def _home(c):
    return c == "US" or c in QUALIFYING


class Instance:
    def __init__(self):
        self.params = json.load(open(os.path.join(DATA, "params.json")))
        self.suppliers = {r["supplier_id"]: r for r in _rows("suppliers.csv")}
        self.products = {r["product_id"]: r for r in _rows("products.csv")}
        self.materials = {r["material_id"]: r for r in _rows("materials.csv")}
        self.slots = {}
        for r in _rows("bom.csv"):
            self.slots.setdefault(r["product_id"], []).append((r["slot"], int(r["qty_per_unit"])))
        self.offers = {r["offer_id"]: r for r in _rows("component_offers.csv")}
        self.slot_offers = {}
        for r in self.offers.values():
            self.slot_offers.setdefault((r["product_id"], r["slot"]), []).append(r["offer_id"])
        self.contents = {}
        for r in _rows("subassembly_contents.csv"):
            self.contents.setdefault(r["assembly_offer_id"], []).append(r)
        self.imports = {r["offer_id"]: r for r in _rows("finished_imports.csv")}
        self.product_imports = {}
        for r in self.imports.values():
            self.product_imports.setdefault(r["product_id"], []).append(r["offer_id"])
        y = int(self.params["delivery_calendar_year"])
        self.threshold = 60 if y < 2024 else (65 if y <= 2028 else 75)
        self.available = set(self.params.get("nonavailable_articles_available_domestically", []))
        self.determinations = set(self.params.get("public_interest_determinations", []))
        self.budget = int(self.params["qualification_budget_cents"])
        self.set_aside = bool(self.params.get("small_business_set_aside"))
        self._status = {}
        self._sm = {mid: self._is_specialty(m) for mid, m in self.materials.items()}

    # ---------------- materials ----------------
    @staticmethod
    def _is_specialty(m):
        pct = {k[4:]: Fraction(v) for k, v in m.items() if k.startswith("max_") and v}
        base = m["base_metal"]
        if base == "iron":
            return any(pct.get(e, 0) > lim for e, lim in STEEL_LIMITS.items()) or \
                any(pct.get(e, 0) > Fraction("0.25") for e in STEEL_ELEMENTS)
        if base in ("titanium", "zirconium"):
            return True
        if base == "nickel":
            return sum(v for e, v in pct.items() if e not in ("ni", "fe")) > 10
        if base == "cobalt":
            return sum(v for e, v in pct.items() if e not in ("co", "fe")) > 10
        return False

    def restricted(self, pid):
        return RESTRICTED_USE[self.products[pid]["next_higher_assembly"]]

    # ---------------- pieces ----------------
    def piece(self, oid):
        o = self.offers[oid]
        if o["supply_type"] == "in_house":
            c = _i(o["inhouse_direct_cents"]) + _i(o["inhouse_overhead_cents"])
            return c, c, c
        p, fr, du = _i(o["unit_price_cents"]), _i(o["freight_cents"]), _i(o["duty_cents"])
        return p + fr + (0 if o["duty_free_certificate"] == "Y" else du), p + fr + du, p + fr + du

    def domestic_component(self, oid):
        o = self.offers[oid]
        c = o["component_origin"]
        if c == "UNKNOWN":
            return False
        if _home(c):
            return True
        art = NONAVAILABLE.get(o["material_class"])
        return art is not None and art not in self.available

    def steel_not_home(self, oid):
        o = self.offers[oid]
        coat = o["metal_coating_country"]
        return not (_home(o["metal_melt_country"]) and _home(o["metal_rolling_country"]) and (coat == "NONE" or _home(coat)))

    def _item(self, origin, form, cots, certified, mid, g, melt, inside_cots_assembly):
        if not mid or not self._sm[mid]:
            return 0, 0, False
        excepted = (form == "electronic" or origin in QUALIFYING or _home(melt)
                    or (form == "fastener" and certified == "Y"))
        if inside_cots_assembly:
            # 252.225-7009(c)(2)(i): COTS assemblies cover their mill products, forgings, castings and
            # fasteners; magnets are covered only inside COTS end items or subsystems
            excepted = excepted or form != "magnet"
        elif cots == "Y" and form not in NOT_COTS_EXCEPTED:
            excepted = True
        if excepted:
            return g, 0, False
        return (g, 0, True) if form == "magnet" else (g, g, False)

    def specialty(self, oid):
        """(grams of specialty metal, grams noncompliant, noncompliant magnet?) for one piece, all tiers."""
        o = self.offers[oid]
        if o["part_form"] != "assembly":
            return self._item(o["component_origin"], o["part_form"], o["component_cots"], o["fastener_mfr_dod_certified"],
                              o["metal_material"], _i(o["metal_g_per_piece"]), o["metal_melt_country"], False)
        G = B = 0
        magnet = False
        made_in_qc = o["component_origin"] in QUALIFYING
        for r in self.contents.get(oid, []):
            q = int(r["qty"])
            g, b, m = self._item(r["item_origin"], r["part_form"], r["component_cots"], "N", r["metal_material"],
                                 _i(r["metal_g_per_piece"]), r["metal_melt_country"], o["component_cots"] == "Y")
            G += q * g
            if not made_in_qc:                 # an item manufactured in a qualifying country is excepted whole
                B += q * b
                magnet = magnet or m
        return G, B, magnet

    def foreign_steel_cost(self, oid):
        """Iron/steel cost not produced in the US or a qualifying country, for one piece."""
        o = self.offers[oid]
        ist = _i(o["iron_steel_cost_cents"])
        if o["part_form"] != "assembly":
            return ist if (ist and self.steel_not_home(oid)) else 0
        f = 0
        for r in self.contents.get(oid, []):
            c = r["metal_coating_country"]
            home = _home(r["metal_melt_country"]) and _home(r["metal_rolling_country"]) and (c in ("NONE", "") or _home(c))
            if not home:
                f += int(r["qty"]) * _i(r["iron_steel_cost_cents"])
        return f

    # ---------------- builds ----------------
    def us_metrics(self, pid, choice):
        prod = self.products[pid]
        outlay = ev = int(prod["assembly_cost_cents"])
        T = Dm = IS = FIS = SG = SB = 0
        magnet = False
        sup = set()
        for slot, q in self.slots[pid]:
            oid = choice[slot]
            po, pc, pe = self.piece(oid)
            outlay += q * po
            ev += q * pe
            T += q * pc
            if self.domestic_component(oid):
                Dm += q * pc
            o = self.offers[oid]
            if o["cots_fastener"] != "Y":
                ist = _i(o["iron_steel_cost_cents"])
                IS += q * ist
                FIS += q * self.foreign_steel_cost(oid)
            g, b, mg = self.specialty(oid)
            SG += q * g
            SB += q * b
            magnet = magnet or mg
            sup.add(o["supplier_id"])
        if 2 * IS > T:
            track = "domestic_iron_steel" if 100 * FIS < 5 * T else "foreign"
        elif prod["cots_item"] == "Y":
            track = "domestic_cots"
        else:
            track = "domestic_component_test" if 100 * Dm > self.threshold * T else "foreign"
        rest = self.restricted(pid)
        return dict(build="us", choice=dict(choice), unit_outlay=outlay, unit_eval=ev, cost_of_components=T,
                    domestic_component_cost=Dm, iron_steel_cost=IS, foreign_iron_steel_cost=FIS, track=track,
                    domestic=track.startswith("domestic"), exempt=False, restricted=rest,
                    specialty_metal_g=SG if rest else None, noncompliant_specialty_metal_g=SB if rest else None,
                    acceptable=(not rest) or (not magnet and 100 * SB <= 2 * SG), suppliers=sup)

    def import_metrics(self, iid):
        r = self.imports[iid]
        pid = r["product_id"]
        c = _i(r["unit_price_cents"]) + _i(r["freight_cents"]) + _i(r["duty_cents"])
        country = r["country_of_manufacture"]
        T, UQ = _i(r["cost_of_components_cents"]), _i(r["us_qc_component_cost_cents"])
        IS, NIS = _i(r["iron_steel_cost_cents"]), _i(r["non_us_qc_iron_steel_cost_cents"])
        qcep = country in QUALIFYING and (self.products[pid]["cots_item"] == "Y" or 100 * UQ > self.threshold * T)
        steel_ok = not (2 * IS > T) or 100 * NIS < 5 * T
        exempt = qcep and steel_ok and (country not in CASE_BY_CASE or country in self.determinations)
        rest = self.restricted(pid)
        SG, SB = _i(r["specialty_metal_g"]), _i(r["noncompliant_specialty_metal_g"])
        if country in QUALIFYING:
            SB = 0
        # 225.872-3(a): a qualifying country end product is not considered in a small business set-aside
        considered = not (self.set_aside and qcep)
        return dict(build="import", import_offer=iid, considered=considered, unit_outlay=c, unit_eval=c,
                    cost_of_components=None,
                    domestic_component_cost=None, iron_steel_cost=None, foreign_iron_steel_cost=None,
                    track="foreign", domestic=False, exempt=exempt,
                    restricted=rest, specialty_metal_g=SG if rest else None,
                    noncompliant_specialty_metal_g=SB if rest else None,
                    acceptable=(not rest) or 100 * SB <= 2 * SG, suppliers={r["supplier_id"]})

    def all_builds(self, pid):
        names = [s for s, _ in self.slots[pid]]
        for combo in itertools.product(*[self.slot_offers[(pid, s)] for s in names]):
            yield self.us_metrics(pid, dict(zip(names, combo)))
        for iid in self.product_imports.get(pid, []):
            yield self.import_metrics(iid)

    # ---------------- evaluation ----------------
    def status(self, pid, builds=None):
        if pid in self._status:
            return self._status[pid]
        offers = [b for b in (builds if builds is not None else self.all_builds(pid))
                  if b["acceptable"] and b.get("considered", True)]
        low = min(b["unit_eval"] for b in offers)
        dom = [b["unit_eval"] for b in offers if b["domestic"]]
        lows = [b for b in offers if b["unit_eval"] == low]
        if any(b["domestic"] for b in lows):
            st = "domestic_required"
        elif not dom:
            st = "foreign_allowed"
        elif any(b["exempt"] for b in lows) or any(b["exempt"] and b["unit_eval"] < min(dom) for b in offers):
            st = "foreign_allowed"
        else:
            st = "domestic_required" if 100 * min(dom) <= 150 * low else "foreign_allowed"
        self._status[pid] = st
        return st

    @staticmethod
    def deliverable(status, b):
        return b["acceptable"] and b.get("considered", True) and (b["domestic"] or status == "foreign_allowed")

    # ---------------- optimum ----------------
    def optimum(self):
        new = sorted(s for s, r in self.suppliers.items() if r["qualified"] != "Y")
        ix = {s: i for i, s in enumerate(new)}
        fee = np.array([int(self.suppliers[s]["qualification_fee_cents"]) for s in new], dtype=float)
        cols, base = [], 0
        for pid in sorted(self.products):
            q = int(self.products[pid]["quantity"])
            builds = list(self.all_builds(pid))
            st = self.status(pid, builds)
            best = {}
            for b in builds:
                if not self.deliverable(st, b):
                    continue
                key = tuple(sorted(s for s in b["suppliers"] if s in ix))
                c = q * b["unit_outlay"]
                if key not in best or c < best[key]:
                    best[key] = c
            m = min(best.values())
            base += m
            cols += [(pid, key, c - m) for key, c in best.items()]
        nz, n = len(cols), len(cols) + len(new)
        c = np.concatenate([np.array([col[2] for col in cols], dtype=float), fee])
        A, lo, hi = [], [], []
        for pid in sorted(self.products):
            r = np.zeros(n)
            r[[j for j, col in enumerate(cols) if col[0] == pid]] = 1
            A.append(r); lo.append(1); hi.append(1)
        for j, (_, key, _) in enumerate(cols):
            for s in key:
                r = np.zeros(n)
                r[j], r[nz + ix[s]] = 1, -1
                A.append(r); lo.append(-np.inf); hi.append(0)
        r = np.zeros(n)
        r[nz:] = fee
        A.append(r); lo.append(-np.inf); hi.append(self.budget)
        res = milp(c, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(n),
                   bounds=Bounds(0, 1), options={"mip_rel_gap": 0, "time_limit": 300})
        assert res.status == 0, res.message
        x = np.round(res.x).astype(int)
        exact = base + sum(cols[j][2] for j in range(nz) if x[j]) + sum(int(fee[i]) for i in range(len(new)) if x[nz + i])
        return exact
