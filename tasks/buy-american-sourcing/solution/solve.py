"""Reference solution: DoD Buy American and specialty metals sourcing plan for the SPE7L3-27-R-0118 bid.

Rules applied:
  * DFARS 252.225-7001 (Basic, FEB 2024). Cost of components = purchased price + freight + U.S. duty
    (even with a duty-free entry certificate); in-house direct + overhead, no profit; assembly excluded.
    Components made in the U.S. or a qualifying country count, as do foreign components of a FAR 25.104
    nonavailable class (unless the solicitation says that article is available domestically); unknown
    origin is foreign. Predominantly iron/steel (COTS fasteners excluded) above 50% of cost of components:
    iron/steel not produced in the U.S. or a qualifying country (every process from melting through
    coating) must be under 5%. Otherwise COTS end products are domestic; others need more than 75%
    (2029 delivery).
  * DFARS 252.225-7009 / 225.7003. For aircraft, missiles, ships, tank or automotive items, weapon systems
    and ammunition (and their components), specialty metal must be melted or produced in the U.S. or a
    qualifying country, except electronic components, COTS items (but not COTS mill products, forgings,
    castings, magnets or fasteners going into a non-COTS item), commercial fasteners whose maker
    certified the 50% domestic purchase, and items manufactured in a qualifying country; up to 2% of the
    specialty metal weight may be otherwise noncompliant, but never in a high performance magnet.
    The restriction reaches every tier: specialty metal inside a purchased sub-assembly counts. A
    sub-assembly made in a qualifying country is excepted as a whole; inside a COTS assembly, forgings,
    castings, mill products, fasteners and parts are excepted but magnets are not (only COTS end items
    and subsystems cover magnets). For Buy American a sub-assembly is one component: only its own
    origin matters.
    Specialty metal: steel above 1.65 Mn / 0.60 Si / 0.60 Cu or above 0.25 of Al, Cr, Co, Mo, Ni, Nb, Ti,
    W, V; nickel or cobalt alloys with more than 10% other alloying metals; titanium and zirconium.
  * DFARS 225.872-3(a): in a small business set-aside, offers of qualifying country end products are not
    considered at all.
  * DFARS 225.502(c)(ii) with the 225.106 50% factor: builds that break the specialty metals rule are not
    acceptable offers; a qualifying country end product (not Austria, which needs a case determination;
    iron/steel ones must also meet the steel test) is exempt from the factor; ties go to domestic.
Then a CP-SAT model chooses one build per product and the vendor audits within budget, minimizing outlay.
"""
import csv
import json
import os
from fractions import Fraction

from ortools.sat.python import cp_model

DATA = os.environ.get("DATA_DIR", "/app/data")
OUT = os.environ.get("OUTPUT_DIR", "/app/output")

QUALIFYING = {"AU", "AT", "BE", "CA", "CZ", "DK", "EG", "EE", "FI", "FR", "DE", "GR", "IL", "IT", "JP", "LV",
              "LT", "LU", "NL", "NO", "PL", "PT", "SI", "ES", "SE", "CH", "TR", "GB"}
CASE_BY_CASE = {"AT"}
NONAVAILABLE = {
    "hog bristles": "Hog bristles for brushes",
    "natural rubber, crude": "Rubber, crude and latex (natural)",
    "quartz crystals": "Quartz crystals",
    "cover glass, microscope slide": "Cover glass, microscope slide",
}
COVERED = ("truck", "hmmwv", "stryker", "machine gun", "weapon")      # 225.7003-2(a)(1) items
NOT_COVERED = ("forklift", "lifter", "ground support", "cots vehicle", "commercial", "facility")


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def n(v):
    return int(v) if v else 0


params = json.load(open(os.path.join(DATA, "params.json")))
year = int(params["delivery_calendar_year"])
THRESHOLD = 60 if year < 2024 else (65 if year <= 2028 else 75)
FACTOR = Fraction(50, 100)
AVAILABLE = set(params.get("nonavailable_articles_available_domestically", []))
EXEMPT_OK = lambda c: c in QUALIFYING and (c not in CASE_BY_CASE or c in params.get("public_interest_determinations", []))
BUDGET = int(params["qualification_budget_cents"])
SET_ASIDE = bool(params.get("small_business_set_aside"))

suppliers = {r["supplier_id"]: r for r in rows("suppliers.csv")}
products = {r["product_id"]: r for r in rows("products.csv")}
materials = {r["material_id"]: r for r in rows("materials.csv")}
slots = {}
for r in rows("bom.csv"):
    slots.setdefault(r["product_id"], []).append((r["slot"], int(r["qty_per_unit"])))
offers = {}
for r in rows("component_offers.csv"):
    offers.setdefault((r["product_id"], r["slot"]), []).append(r)
contents = {}
for r in rows("subassembly_contents.csv"):
    contents.setdefault(r["assembly_offer_id"], []).append(r)
imports = {}
for r in rows("finished_imports.csv"):
    imports.setdefault(r["product_id"], []).append(r)


def ok_country(c):
    return c == "US" or c in QUALIFYING


def specialty_metal(mid):
    if not mid:
        return False
    m = materials[mid]
    el = {k[4:]: Fraction(v) for k, v in m.items() if k.startswith("max_") and v}
    base = m["base_metal"]
    if base == "iron":
        return (el.get("mn", 0) > Fraction("1.65") or el.get("si", 0) > Fraction("0.60") or el.get("cu", 0) > Fraction("0.60")
                or any(el.get(e, 0) > Fraction("0.25") for e in ("al", "cr", "co", "mo", "ni", "nb", "ti", "w", "v")))
    if base in ("titanium", "zirconium"):
        return True
    if base in ("nickel", "cobalt"):
        keep = ("ni", "fe") if base == "nickel" else ("co", "fe")
        return sum(v for e, v in el.items() if e not in keep) > 10
    return False


def covered(pid):
    use = products[pid]["next_higher_assembly"].lower()
    if any(k in use for k in NOT_COVERED):
        return False
    return any(k in use for k in COVERED)


def item_metal(origin, form, cots, certified, mid, grams, melt, in_cots_assembly=False):
    """(specialty metal grams, noncompliant grams, noncompliant magnet?) for one item."""
    if not specialty_metal(mid):
        return 0, 0, False
    if form == "electronic" or origin in QUALIFYING or ok_country(melt):
        return grams, 0, False
    if in_cots_assembly and form != "magnet":
        return grams, 0, False
    if not in_cots_assembly and cots == "Y" and form not in ("mill_product", "forging", "casting", "magnet", "fastener"):
        return grams, 0, False
    if form == "fastener" and certified == "Y":
        return grams, 0, False
    return (grams, 0, True) if form == "magnet" else (grams, grams, False)


def assembly_metal(o):
    total = bad = 0
    magnet = False
    for r in contents.get(o["offer_id"], []):
        q = int(r["qty"])
        g = n(r["metal_g_per_piece"])
        if o["component_origin"] in QUALIFYING:          # item manufactured in a qualifying country
            total += q * (g if specialty_metal(r["metal_material"]) else 0)
            continue
        w, b, m = item_metal(r["item_origin"], r["part_form"], r["component_cots"], "N", r["metal_material"], g,
                             r["metal_melt_country"], in_cots_assembly=o["component_cots"] == "Y")
        total += q * w
        bad += q * b
        magnet = magnet or m
    return total, bad, magnet


def offer_terms(o):
    if o["supply_type"] == "in_house":
        cc = n(o["inhouse_direct_cents"]) + n(o["inhouse_overhead_cents"])
        outlay = ev = cc
    else:
        base = n(o["unit_price_cents"]) + n(o["freight_cents"])
        duty = n(o["duty_cents"])
        cc = ev = base + duty
        outlay = base + (0 if o["duty_free_certificate"] == "Y" else duty)
    org = o["component_origin"]
    if org == "UNKNOWN":
        dom = False
    elif ok_country(org):
        dom = True
    else:
        art = NONAVAILABLE.get(o["material_class"])
        dom = art is not None and art not in AVAILABLE
    ist = 0 if o["cots_fastener"] == "Y" else n(o["iron_steel_cost_cents"])
    steps = [o["metal_melt_country"], o["metal_rolling_country"]]
    if o["metal_coating_country"] not in ("", "NONE"):
        steps.append(o["metal_coating_country"])
    fis = ist if (ist and not all(ok_country(s) for s in steps)) else 0
    if o["part_form"] == "assembly":
        fis = 0
        for r in contents.get(o["offer_id"], []):
            st = [r["metal_melt_country"], r["metal_rolling_country"]] + (
                [r["metal_coating_country"]] if r["metal_coating_country"] not in ("", "NONE") else [])
            if n(r["iron_steel_cost_cents"]) and not all(ok_country(x) for x in st):
                fis += int(r["qty"]) * n(r["iron_steel_cost_cents"])
        smw, bad, magnet_bad = assembly_metal(o)
    else:
        smw, bad, magnet_bad = item_metal(org, o["part_form"], o["component_cots"], o["fastener_mfr_dod_certified"],
                                          o["metal_material"], n(o["metal_g_per_piece"]), o["metal_melt_country"])
    return dict(outlay=outlay, cc=cc, ev=ev, dom=dom, ist=ist, fis=fis, smw=smw, bad=bad, magnet_bad=magnet_bad)


TERMS = {o["offer_id"]: offer_terms(o) for lst in offers.values() for o in lst}


def import_terms(pid, r):
    cost = n(r["unit_price_cents"]) + n(r["freight_cents"]) + n(r["duty_cents"])
    country = r["country_of_manufacture"]
    T, UQ = n(r["cost_of_components_cents"]), n(r["us_qc_component_cost_cents"])
    IS, NIS = n(r["iron_steel_cost_cents"]), n(r["non_us_qc_iron_steel_cost_cents"])
    qcep = country in QUALIFYING and (products[pid]["cots_item"] == "Y" or Fraction(UQ) > Fraction(T) * Fraction(THRESHOLD, 100))
    pred = Fraction(IS) > Fraction(T) / 2
    exempt = qcep and EXEMPT_OK(country) and (not pred or Fraction(NIS) < Fraction(T) * Fraction(5, 100))
    smt, smb = n(r["specialty_metal_g"]), n(r["noncompliant_specialty_metal_g"])
    if country in QUALIFYING:
        smb = 0
    sm_ok = (not covered(pid)) or Fraction(smb) <= Fraction(smt) * Fraction(2, 100)
    considered = not (SET_ASIDE and qcep)          # 225.872-3(a)
    return dict(cost=cost, qcep=qcep, exempt=exempt and considered, smt=smt, smb=smb, sm_ok=sm_ok,
                considered=considered)


class ProductModel:
    def __init__(self, m, pid):
        self.pid = pid
        self.cots = products[pid]["cots_item"] == "Y"
        self.covered = covered(pid)
        self.x = {}
        self.us = m.NewBoolVar(f"us_{pid}")
        self.imp = {r["offer_id"]: m.NewBoolVar(f"imp_{r['offer_id']}") for r in imports.get(pid, [])}
        self.iterms = {r["offer_id"]: import_terms(pid, r) for r in imports.get(pid, [])}
        m.Add(self.us + sum(self.imp.values()) == 1)
        T, Dm, IS, FIS, OUTL, EV, SMW, SMB = [], [], [], [], [], [], [], []
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
                SMW.append(q * t["smw"] * v)
                SMB.append(q * t["bad"] * v)
                if self.covered and t["magnet_bad"]:
                    m.Add(v == 0)
            m.Add(sum(row) == self.us)
        asm = int(products[pid]["assembly_cost_cents"])
        for oid, v in self.imp.items():
            OUTL.append(self.iterms[oid]["cost"] * v)
            EV.append(self.iterms[oid]["cost"] * v)
            if not self.iterms[oid]["sm_ok"] or not self.iterms[oid]["considered"]:
                m.Add(v == 0)
        self.T, self.Dm, self.IS, self.FIS = sum(T), sum(Dm), sum(IS), sum(FIS)
        self.outlay = sum(OUTL) + asm * self.us
        self.ev = sum(EV) + asm * self.us
        if self.covered:
            m.Add(100 * sum(SMB) <= 2 * sum(SMW))
        self.SMW, self.SMB = SMW, SMB
        self.pred = m.NewBoolVar(f"pred_{pid}")
        m.Add(2 * self.IS - self.T >= 1).OnlyEnforceIf(self.pred)
        m.Add(2 * self.IS - self.T <= 0).OnlyEnforceIf(self.pred.Not())
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

    def domestic(self):
        return [self.r_steel, self.r_cots, self.r_comp]

    def chosen(self, solver):
        for oid, v in self.imp.items():
            if solver.Value(v):
                return ("import", oid)
        return ("us", {s: next(o["offer_id"] for o in offers[(self.pid, s)] if solver.Value(self.x[o["offer_id"]]))
                       for s, _ in slots[self.pid]})


def min_eval(pid, domestic_only):
    m = cp_model.CpModel()
    pm = ProductModel(m, pid)
    if domestic_only:
        m.AddBoolOr(pm.domestic())
    m.Minimize(pm.ev)
    s = cp_model.CpSolver()
    s.parameters.num_workers = 1
    st = s.Solve(m)
    if st == cp_model.INFEASIBLE:
        return None
    assert st == cp_model.OPTIMAL
    return int(round(s.ObjectiveValue()))


def admissibility(pid):
    """DFARS 225.502(c)(ii), price the determining factor, over acceptable (specialty-metal compliant) offers."""
    low = min_eval(pid, False)
    dom = min_eval(pid, True)
    if dom is None or dom == low:
        return "domestic_required" if dom is not None else "foreign_allowed"
    exempt = [t["cost"] for t in (import_terms(pid, r) for r in imports.get(pid, [])) if t["exempt"] and t["sm_ok"]]
    if exempt and min(exempt) == low:
        return "foreign_allowed"                       # (C) low offer is an exempt qualifying country offer
    if exempt and min(exempt) < dom:
        return "foreign_allowed"                       # (D)
    if Fraction(dom) <= Fraction(low) * (1 + FACTOR):
        return "domestic_required"                     # (E)(1), ties to domestic
    return "foreign_allowed"                           # (E)(2)


def main():
    status = {pid: admissibility(pid) for pid in sorted(products)}
    m = cp_model.CpModel()
    pms = {pid: ProductModel(m, pid) for pid in sorted(products)}
    for pid, pm in pms.items():
        if status[pid] == "domestic_required":
            m.AddBoolOr(pm.domestic())
    new = sorted(s for s, r in suppliers.items() if r["qualified"] != "Y")
    y = {s: m.NewBoolVar(f"q_{s}") for s in new}
    for pid, pm in pms.items():
        for s_, q in slots[pid]:
            for o in offers[(pid, s_)]:
                if o["supplier_id"] in y:
                    m.AddImplication(pm.x[o["offer_id"]], y[o["supplier_id"]])
        for r in imports.get(pid, []):
            if r["supplier_id"] in y:
                m.AddImplication(pm.imp[r["offer_id"]], y[r["supplier_id"]])
    fee = {s: int(suppliers[s]["qualification_fee_cents"]) for s in new}
    m.Add(sum(fee[s] * y[s] for s in new) <= BUDGET)
    m.Minimize(sum(int(products[p]["quantity"]) * pm.outlay for p, pm in pms.items()) + sum(fee[s] * y[s] for s in new))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 2
    solver.parameters.max_time_in_seconds = 900
    st = solver.Solve(m)
    assert st == cp_model.OPTIMAL, solver.StatusName(st)

    lines, used, total = [], set(), 0
    for pid, pm in pms.items():
        kind, choice = pm.chosen(solver)
        q = int(products[pid]["quantity"])
        if kind == "import":
            r = next(r for r in imports[pid] if r["offer_id"] == choice)
            t = pm.iterms[choice]
            used.add(r["supplier_id"])
            unit = t["cost"]
            line = dict(product_id=pid, admissibility=status[pid], build="import", offers=None, import_offer=choice,
                        unit_outlay_cents=unit, cost_of_components_cents=None, domestic_component_cost_cents=None,
                        iron_steel_cost_cents=None, foreign_iron_steel_cost_cents=None,
                        track="foreign",
                        specialty_metals_restricted=pm.covered, specialty_metal_g=t["smt"] if pm.covered else None,
                        noncompliant_specialty_metal_g=t["smb"] if pm.covered else None)
        else:
            T = Dm = IS = FIS = SW = SB = 0
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
                SW += qty * t["smw"]
                SB += qty * t["bad"]
            if Fraction(IS) > Fraction(T) / 2:
                track = "domestic_iron_steel" if Fraction(FIS) < Fraction(T) * Fraction(5, 100) else "foreign"
            elif pm.cots:
                track = "domestic_cots"
            else:
                track = "domestic_component_test" if Fraction(Dm) > Fraction(T) * Fraction(THRESHOLD, 100) else "foreign"
            line = dict(product_id=pid, admissibility=status[pid], build="us", offers=choice, import_offer=None,
                        unit_outlay_cents=unit, cost_of_components_cents=T, domestic_component_cost_cents=Dm,
                        iron_steel_cost_cents=IS, foreign_iron_steel_cost_cents=FIS, track=track,
                        specialty_metals_restricted=pm.covered, specialty_metal_g=SW if pm.covered else None,
                        noncompliant_specialty_metal_g=SB if pm.covered else None)
        total += q * unit
        lines.append(line)
    newq = sorted(s for s in new if solver.Value(y[s]) and s in used)
    spend = sum(fee[s] for s in newq)
    total += spend
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "plan.json"), "w") as f:
        json.dump(dict(total_outlay_cents=total, qualification_spend_cents=spend, new_qualifications=newq, lines=lines),
                  f, indent=2)
    print(f"total outlay {total} cents, new qualifications {newq}, spend {spend}")


if __name__ == "__main__":
    main()
