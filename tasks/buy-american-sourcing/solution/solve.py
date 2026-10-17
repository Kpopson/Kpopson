"""Reference solution: Buy American sourcing plan for the FSS-26-0418 bid.

Rules applied (FAR 25.101, 25.106, 25.502, 25.504-1 and clause 52.225-1, Oct 2022):
  * cost of components = purchased: price + freight + duty (duty counts even with a
    duty-free entry certificate); in-house: direct + overhead, no profit. End-product
    assembly is not a component cost.
  * domestic component = made in the US, or a foreign component of a 25.104 nonavailable
    class (unless the solicitation says that article is available domestically).
    Unknown origin is foreign.
  * predominantly iron/steel when iron and steel content (COTS fasteners excluded)
    exceeds 50% of cost of components; then foreign iron/steel must be under 5%.
    Steel is domestic only if melting, rolling and coating all happened in the US.
  * otherwise COTS end products are domestic (waiver); others need domestic components
    to exceed 75% (2029 delivery).
  * per product, the foreign build may be delivered only if the low build is foreign
    and the 30% (small business) factor still leaves it strictly below the cheapest
    domestic build; the 55% fallback of 25.106(b)(2) is applied before 2030.
Then a CP-SAT model picks one build per product, which new vendors to qualify within
the audit budget, and minimizes total outlay.
"""
import csv
import json
import os
from fractions import Fraction

from ortools.sat.python import cp_model

DATA = os.environ.get("DATA_DIR", "/app/data")
OUT = os.environ.get("OUTPUT_DIR", "/app/output")

NONAVAILABLE = {
    "hog bristles": "Hog bristles for brushes",
    "natural rubber, crude": "Rubber, crude and latex (natural)",
    "quartz crystals": "Quartz crystals",
    "cover glass, microscope slide": "Cover glass, microscope slide",
    "jute burlap": "Fibers of the following types: abaca, abace, agave, coir, flax, jute, jute burlaps, palmyra, and sisal",
    "tin bars": "Tin in bars, blocks, and pigs",
}


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def n(v):
    return int(v) if v else 0


params = json.load(open(os.path.join(DATA, "params.json")))
year = int(params["delivery_calendar_year"])
THRESHOLD = 60 if year < 2024 else (65 if year <= 2028 else 75)
FACTOR = Fraction(30 if params["offeror_size"] == "small" else 20, 100)
FALLBACK = params["evaluation_date"] < "2030-01-01"
AVAILABLE = set(params.get("nonavailable_articles_available_domestically", []))
BUDGET = int(params["qualification_budget_cents"])

suppliers = {r["supplier_id"]: r for r in rows("suppliers.csv")}
products = {r["product_id"]: r for r in rows("products.csv")}
slots = {}
for r in rows("bom.csv"):
    slots.setdefault(r["product_id"], []).append((r["slot"], int(r["qty_per_unit"])))
offers = {}
for r in rows("component_offers.csv"):
    offers.setdefault((r["product_id"], r["slot"]), []).append(r)
imports = {}
for r in rows("finished_imports.csv"):
    imports.setdefault(r["product_id"], []).append(r)


def offer_terms(o):
    """Per piece: outlay, cost of component, evaluated cost (with duty), domestic?, iron/steel, foreign iron/steel."""
    if o["supply_type"] == "in_house":
        cc = n(o["inhouse_direct_cents"]) + n(o["inhouse_overhead_cents"])
        outlay = ev = cc
    else:
        base = n(o["unit_price_cents"]) + n(o["freight_cents"])
        duty = n(o["duty_cents"])
        cc = ev = base + duty
        outlay = base + (0 if o["duty_free_certificate"] == "Y" else duty)
    org = o["component_origin"]
    if org == "US":
        dom = True
    elif org == "UNKNOWN":
        dom = False
    else:
        art = NONAVAILABLE.get(o["material_class"])
        dom = art is not None and art not in AVAILABLE
    ist = 0 if o["cots_fastener"] == "Y" else n(o["iron_steel_cost_cents"])
    steps = [o["steel_melt_country"], o["steel_rolling_country"]]
    if o["steel_coating_country"] != "NONE":
        steps.append(o["steel_coating_country"])
    fis = ist if (ist and any(s != "US" for s in steps)) else 0
    return dict(outlay=outlay, cc=cc, ev=ev, dom=dom, ist=ist, fis=fis)


TERMS = {o["offer_id"]: offer_terms(o) for lst in offers.values() for o in lst}


def import_cost(r):
    return n(r["unit_price_cents"]) + n(r["freight_cents"]) + n(r["duty_cents"])


class ProductModel:
    """CP-SAT pieces describing one product's possible builds."""

    def __init__(self, m, pid):
        self.pid = pid
        self.cots = products[pid]["cots_item"] == "Y"
        self.x = {}
        self.us = m.NewBoolVar(f"us_{pid}")
        self.imp = {r["offer_id"]: m.NewBoolVar(f"imp_{r['offer_id']}") for r in imports.get(pid, [])}
        m.Add(self.us + sum(self.imp.values()) == 1)
        T, Dm, IS, FIS, OUTL, EV = [], [], [], [], [], []
        for s, q in slots[pid]:
            row = []
            for o in offers[(pid, s)]:
                v = m.NewBoolVar(f"x_{o['offer_id']}")
                self.x[o["offer_id"]] = v
                row.append(v)
                t = TERMS[o["offer_id"]]
                T.append(q * t["cc"] * v)
                if t["dom"]:
                    Dm.append(q * t["cc"] * v)
                IS.append(q * t["ist"] * v)
                FIS.append(q * t["fis"] * v)
                OUTL.append(q * t["outlay"] * v)
                EV.append(q * t["ev"] * v)
            m.Add(sum(row) == self.us)
        asm = int(products[pid]["assembly_cost_cents"])
        for oid, v in self.imp.items():
            c = import_cost(next(r for r in imports[pid] if r["offer_id"] == oid))
            OUTL.append(c * v)
            EV.append(c * v)
        self.T, self.Dm, self.IS, self.FIS = sum(T), sum(Dm), sum(IS), sum(FIS)
        self.outlay = sum(OUTL) + asm * self.us
        self.ev = sum(EV) + asm * self.us
        # predominantly iron or steel: iron and steel content exceeds 50% of cost of components
        self.pred = m.NewBoolVar(f"pred_{pid}")
        m.Add(2 * self.IS - self.T >= 1).OnlyEnforceIf(self.pred)
        m.Add(2 * self.IS - self.T <= 0).OnlyEnforceIf(self.pred.Not())
        # routes to a domestic end product
        self.r_steel = m.NewBoolVar(f"rs_{pid}")
        m.AddImplication(self.r_steel, self.pred)
        m.AddImplication(self.r_steel, self.us)
        m.Add(20 * self.FIS - self.T <= -1).OnlyEnforceIf(self.r_steel)
        self.r_cots = m.NewBoolVar(f"rc_{pid}")
        if not self.cots:
            m.Add(self.r_cots == 0)
        m.AddImplication(self.r_cots, self.pred.Not())
        m.AddImplication(self.r_cots, self.us)
        self.r_comp = m.NewBoolVar(f"rd_{pid}")
        if self.cots:
            m.Add(self.r_comp == 0)
        m.AddImplication(self.r_comp, self.pred.Not())
        m.AddImplication(self.r_comp, self.us)
        m.Add(100 * self.Dm - THRESHOLD * self.T >= 1).OnlyEnforceIf(self.r_comp)
        # 25.106(b)(2) fallback build: US-made, not COTS, not predominantly iron/steel, over 55%
        self.r_fb = m.NewBoolVar(f"rf_{pid}")
        if self.cots:
            m.Add(self.r_fb == 0)
        m.AddImplication(self.r_fb, self.pred.Not())
        m.AddImplication(self.r_fb, self.us)
        m.Add(100 * self.Dm - 55 * self.T >= 1).OnlyEnforceIf(self.r_fb)

    def domestic(self):
        return [self.r_steel, self.r_cots, self.r_comp]

    def chosen(self, solver):
        for oid, v in self.imp.items():
            if solver.Value(v):
                return ("import", oid)
        return ("us", {s: next(o["offer_id"] for o in offers[(self.pid, s)] if solver.Value(self.x[o["offer_id"]]))
                       for s, _ in slots[self.pid]})


def min_eval(pid, route):
    """Lowest evaluated unit cost of a build of pid satisfying route (None if infeasible)."""
    m = cp_model.CpModel()
    pm = ProductModel(m, pid)
    if route == "domestic":
        m.AddBoolOr(pm.domestic())
    elif route == "fallback":
        m.Add(pm.r_fb == 1)
    m.Minimize(pm.ev)
    s = cp_model.CpSolver()
    s.parameters.num_workers = 1
    st = s.Solve(m)
    if st == cp_model.INFEASIBLE:
        return None
    assert st == cp_model.OPTIMAL
    return int(round(s.ObjectiveValue()))


def low_offer_over_55(pid, low):
    """Is there a build at the low evaluated price with more than 55% domestic content?"""
    m = cp_model.CpModel()
    pm = ProductModel(m, pid)
    m.Add(pm.ev == low)
    m.Add(pm.us == 1)
    m.Add(100 * pm.Dm - 55 * pm.T >= 1)
    s = cp_model.CpSolver()
    s.parameters.num_workers = 1
    return s.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def admissibility(pid):
    low = min_eval(pid, "any")
    dom = min_eval(pid, "domestic")
    if dom is not None and dom == low:
        return "domestic_required"          # low offer is domestic: award on it
    evaluated = Fraction(low) * (1 + FACTOR)
    if dom is not None and Fraction(dom) <= evaluated:
        return "domestic_required"          # domestic not unreasonable (tie goes to domestic)
    if FALLBACK and products[pid]["cots_item"] != "Y" and not low_offer_over_55(pid, low):
        fb = min_eval(pid, "fallback")
        if fb is not None and Fraction(fb) <= evaluated:
            return "fallback_required"
    return "foreign_allowed"


def main():
    status = {pid: admissibility(pid) for pid in sorted(products)}
    m = cp_model.CpModel()
    pms = {pid: ProductModel(m, pid) for pid in sorted(products)}
    for pid, pm in pms.items():
        if status[pid] == "domestic_required":
            m.AddBoolOr(pm.domestic())
        elif status[pid] == "fallback_required":
            m.AddBoolOr(pm.domestic() + [pm.r_fb])
    new = sorted(s for s, r in suppliers.items() if r["qualified"] != "Y")
    y = {s: m.NewBoolVar(f"q_{s}") for s in new}
    for pid, pm in pms.items():
        for (p, s_), lst in offers.items():
            if p != pid:
                continue
            for o in lst:
                if o["supplier_id"] in y:
                    m.AddImplication(pm.x[o["offer_id"]], y[o["supplier_id"]])
        for r in imports.get(pid, []):
            if r["supplier_id"] in y:
                m.AddImplication(pm.imp[r["offer_id"]], y[r["supplier_id"]])
    fee = {s: int(suppliers[s]["qualification_fee_cents"]) for s in new}
    m.Add(sum(fee[s] * y[s] for s in new) <= BUDGET)
    m.Minimize(sum(int(products[p]["quantity"]) * pm.outlay for p, pm in pms.items())
               + sum(fee[s] * y[s] for s in new))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 2
    solver.parameters.max_time_in_seconds = 600
    st = solver.Solve(m)
    assert st == cp_model.OPTIMAL, solver.StatusName(st)

    lines = []
    used = set()
    total = 0
    for pid, pm in pms.items():
        kind, choice = pm.chosen(solver)
        q = int(products[pid]["quantity"])
        if kind == "import":
            r = next(r for r in imports[pid] if r["offer_id"] == choice)
            used.add(r["supplier_id"])
            unit = import_cost(r)
            line = dict(product_id=pid, admissibility=status[pid], build="import", offers=None, import_offer=choice,
                        unit_outlay_cents=unit, cost_of_components_cents=None, domestic_component_cost_cents=None,
                        iron_steel_cost_cents=None, foreign_iron_steel_cost_cents=None, track="foreign")
        else:
            T = Dm = IS = FIS = 0
            unit = int(products[pid]["assembly_cost_cents"])
            for s, qty in slots[pid]:
                o = next(o for o in offers[(pid, s)] if o["offer_id"] == choice[s])
                used.add(o["supplier_id"])
                t = TERMS[o["offer_id"]]
                unit += qty * t["outlay"]
                T += qty * t["cc"]
                Dm += qty * t["cc"] if t["dom"] else 0
                IS += qty * t["ist"]
                FIS += qty * t["fis"]
            pred = Fraction(IS) > Fraction(T) / 2
            cots = products[pid]["cots_item"] == "Y"
            if pred:
                track = "domestic_iron_steel" if Fraction(FIS) < Fraction(T) * Fraction(5, 100) else "foreign"
            elif cots:
                track = "domestic_cots"
            else:
                track = "domestic_component_test" if Fraction(Dm) > Fraction(T) * Fraction(THRESHOLD, 100) else "foreign"
            line = dict(product_id=pid, admissibility=status[pid], build="us", offers=choice, import_offer=None,
                        unit_outlay_cents=unit, cost_of_components_cents=T, domestic_component_cost_cents=Dm,
                        iron_steel_cost_cents=IS, foreign_iron_steel_cost_cents=FIS, track=track)
        total += q * unit
        lines.append(line)
    newq = sorted(s for s in new if solver.Value(y[s]) and s in used)
    spend = sum(fee[s] for s in newq)
    total += spend
    os.makedirs(OUT, exist_ok=True)
    plan = dict(total_outlay_cents=total, qualification_spend_cents=spend, new_qualifications=newq, lines=lines)
    with open(os.path.join(OUT, "plan.json"), "w") as f:
        json.dump(plan, f, indent=2)
    print(f"total outlay {total} cents, new qualifications {newq}, spend {spend}")


if __name__ == "__main__":
    main()
