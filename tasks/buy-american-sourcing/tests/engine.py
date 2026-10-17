"""Independent verifier engine for the buy-american-sourcing task.

Reads only /tests/data. Applies FAR 25.101, 25.106, 25.502 and clause 52.225-1
(Oct 2022) in exact integer arithmetic by enumerating every build of every product,
then finds the minimum total outlay with a selection MILP (HiGHS via scipy).
Written independently of the reference solution, which uses a CP-SAT model.
"""
import csv
import itertools
import json
import os

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

DATA = os.environ.get("VERIFIER_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

# material_class values in the data that are FAR 25.104(a) nonavailable articles
NONAVAILABLE = {
    "hog bristles": "Hog bristles for brushes",
    "natural rubber, crude": "Rubber, crude and latex (natural)",
    "quartz crystals": "Quartz crystals",
    "cover glass, microscope slide": "Cover glass, microscope slide",
    "jute burlap": "Fibers of the following types: abaca, abace, agave, coir, flax, jute, jute burlaps, palmyra, and sisal",
    "tin bars": "Tin in bars, blocks, and pigs",
}

TRACKS = ("domestic_component_test", "domestic_iron_steel", "domestic_cots", "foreign")
STATUSES = ("domestic_required", "fallback_required", "foreign_allowed")


def _rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _i(v):
    return int(v) if v not in ("", None) else 0


class Instance:
    def __init__(self):
        self.params = json.load(open(os.path.join(DATA, "params.json")))
        self.suppliers = {r["supplier_id"]: r for r in _rows("suppliers.csv")}
        self.products = {r["product_id"]: r for r in _rows("products.csv")}
        self.slots = {}
        for r in _rows("bom.csv"):
            self.slots.setdefault(r["product_id"], []).append((r["slot"], int(r["qty_per_unit"])))
        self.offers = {r["offer_id"]: r for r in _rows("component_offers.csv")}
        self.slot_offers = {}
        for r in self.offers.values():
            self.slot_offers.setdefault((r["product_id"], r["slot"]), []).append(r["offer_id"])
        self.imports = {r["offer_id"]: r for r in _rows("finished_imports.csv")}
        self.product_imports = {}
        for r in self.imports.values():
            self.product_imports.setdefault(r["product_id"], []).append(r["offer_id"])
        y = int(self.params["delivery_calendar_year"])
        self.threshold = 60 if y < 2024 else (65 if y <= 2028 else 75)
        self.factor = 30 if self.params["offeror_size"] == "small" else 20
        self.fallback = self.params["evaluation_date"] < "2030-01-01"
        self.available = set(self.params.get("nonavailable_articles_available_domestically", []))
        self.budget = int(self.params["qualification_budget_cents"])

    # ---------------- pieces ----------------
    def piece(self, oid):
        o = self.offers[oid]
        if o["supply_type"] == "in_house":
            c = _i(o["inhouse_direct_cents"]) + _i(o["inhouse_overhead_cents"])
            return c, c, c
        p, fr, du = _i(o["unit_price_cents"]), _i(o["freight_cents"]), _i(o["duty_cents"])
        outlay = p + fr + (0 if o["duty_free_certificate"] == "Y" else du)
        return outlay, p + fr + du, p + fr + du   # outlay, cost of component, evaluated

    def domestic_component(self, oid):
        o = self.offers[oid]
        if o["component_origin"] == "US":
            return True
        if o["component_origin"] == "UNKNOWN":
            return False
        art = NONAVAILABLE.get(o["material_class"])
        return art is not None and art not in self.available

    def foreign_steel(self, oid):
        o = self.offers[oid]
        # produced in the US = melting through coating all in the US; ore origin irrelevant
        return not (o["steel_melt_country"] == "US" and o["steel_rolling_country"] == "US"
                    and o["steel_coating_country"] in ("US", "NONE"))

    # ---------------- builds ----------------
    def us_metrics(self, pid, choice):
        prod = self.products[pid]
        outlay = int(prod["assembly_cost_cents"])
        ev = outlay
        T = Dm = IS = FIS = 0
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
                if ist and self.foreign_steel(oid):
                    FIS += q * ist
            sup.add(o["supplier_id"])
        pred = 2 * IS > T
        cots = prod["cots_item"] == "Y"
        if pred:
            track = "domestic_iron_steel" if 100 * FIS < 5 * T else "foreign"
        elif cots:
            track = "domestic_cots"
        else:
            track = "domestic_component_test" if 100 * Dm > self.threshold * T else "foreign"
        fallback_ok = (not cots) and (not pred) and 100 * Dm > 55 * T
        return dict(build="us", choice=dict(choice), unit_outlay=outlay, unit_eval=ev,
                    cost_of_components=T, domestic_component_cost=Dm, iron_steel_cost=IS,
                    foreign_iron_steel_cost=FIS, track=track, fallback_ok=fallback_ok,
                    over55=100 * Dm > 55 * T, suppliers=sup)

    def import_metrics(self, iid):
        r = self.imports[iid]
        c = _i(r["unit_price_cents"]) + _i(r["freight_cents"]) + _i(r["duty_cents"])
        return dict(build="import", import_offer=iid, unit_outlay=c, unit_eval=c,
                    cost_of_components=None, domestic_component_cost=None, iron_steel_cost=None,
                    foreign_iron_steel_cost=None, track="foreign", fallback_ok=False, over55=False,
                    suppliers={r["supplier_id"]})

    def all_builds(self, pid):
        names = [s for s, _ in self.slots[pid]]
        for combo in itertools.product(*[self.slot_offers[(pid, s)] for s in names]):
            yield self.us_metrics(pid, dict(zip(names, combo)))
        for iid in self.product_imports.get(pid, []):
            yield self.import_metrics(iid)

    # ---------------- evaluation ----------------
    def status(self, pid, builds=None):
        builds = list(builds if builds is not None else self.all_builds(pid))
        low = min(b["unit_eval"] for b in builds)
        at_low = [b for b in builds if b["unit_eval"] == low]
        if any(b["track"] != "foreign" for b in at_low):
            return "domestic_required"
        dom = [b["unit_eval"] for b in builds if b["track"] != "foreign"]
        f = self.factor
        # domestic offer is reasonable when it does not exceed low * (1 + f/100); ties go to domestic
        if dom and 100 * min(dom) <= (100 + f) * low:
            return "domestic_required"
        if self.fallback and self.products[pid]["cots_item"] != "Y" and not any(b["over55"] for b in at_low):
            fb = [b["unit_eval"] for b in builds if b["fallback_ok"]]
            if fb and 100 * min(fb) <= (100 + f) * low:
                return "fallback_required"
        return "foreign_allowed"

    @staticmethod
    def deliverable(status, b):
        if b["track"] != "foreign":
            return True
        if status == "foreign_allowed":
            return True
        return status == "fallback_required" and b["fallback_ok"]

    # ---------------- optimum ----------------
    def optimum(self):
        new = sorted(s for s, r in self.suppliers.items() if r["qualified"] != "Y")
        ix = {s: i for i, s in enumerate(new)}
        fee = np.array([int(self.suppliers[s]["qualification_fee_cents"]) for s in new], dtype=float)
        cols, base, statuses = [], 0, {}
        for pid in sorted(self.products):
            q = int(self.products[pid]["quantity"])
            builds = list(self.all_builds(pid))
            st = self.status(pid, builds)
            statuses[pid] = st
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
        pids = sorted(self.products)
        for pid in pids:
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
        exact = base + sum(cols[j][2] for j in range(nz) if x[j]) + sum(
            int(fee[i]) for i in range(len(new)) if x[nz + i])
        return exact, statuses
