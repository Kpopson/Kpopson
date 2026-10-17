"""Development rules engine for the buy-american-sourcing task.

Implements FAR 25.101, 25.106, 25.502 and clause 52.225-1 (Oct 2022) the way the
task grades them, plus SHORTCUT flags that reproduce plausible wrong readings so
calibrate.py can prove each one fails a test. Never uploaded.

Optimizer: enumerate every build of every product, filter by the rules in exact
integer arithmetic, collapse builds that need the same set of not-yet-qualified
suppliers, then solve a small selection MILP with HiGHS (scipy.optimize.milp).
"""
import csv
import itertools
import json
import os
from fractions import Fraction

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

# FAR 25.104(a) entries that the data's material_class values belong to.
LISTED_CLASSES = {
    "hog bristles": "Hog bristles for brushes",
    "natural rubber, crude": "Rubber, crude and latex (natural)",
    "quartz crystals": "Quartz crystals",
    "cover glass, microscope slide": "Cover glass, microscope slide",
    "jute burlap": "Fibers of the following types: abaca, abace, agave, coir, flax, jute, jute burlaps, palmyra, and sisal",
    "tin bars": "Tin in bars, blocks, and pigs",
}

SHORTCUTS = {
    "nonstrict": "uses >= / <= where the clause says exceeds / less than",
    "stale_threshold": "uses 65% for a 2029 delivery",
    "unknown_domestic": "treats components of unknown origin as domestic",
    "cert_no_duty": "drops duty from cost of components when a duty-free entry certificate is issued",
    "ignore_list": "ignores the 25.104 nonavailable list",
    "ignore_notice": "applies the 25.104 list even to the article the solicitation says is available domestically",
    "no_cots_waiver": "applies the component test to COTS end products",
    "cots_waives_steel": "lets the COTS waiver cover predominantly iron/steel products",
    "count_fasteners": "counts COTS fasteners in iron and steel content",
    "melt_only": "decides steel origin by melt country only",
    "last_process": "decides steel origin by the last processing step only",
    "ore_matters": "treats steel made from foreign ore as foreign",
    "steel_is_component_origin": "uses steel origin as component origin in the component test",
    "factor20": "uses the 20% large-business factor",
    "tie_foreign": "awards the foreign build when evaluated price ties the domestic build",
    "no_fallback": "ignores the 55% fallback in 25.106(b)(2)",
    "profit_in_cost": "includes in-house profit in cost of components",
    "assembly_in_cost": "adds end-product assembly cost to cost of components (as domestic)",
}

TRACKS = ("domestic_component_test", "domestic_iron_steel", "domestic_cots", "foreign")


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _int(v):
    return int(v) if v not in ("", None) else 0


def load(data_dir):
    params = json.load(open(os.path.join(data_dir, "params.json")))
    suppliers = {r["supplier_id"]: r for r in _rows(os.path.join(data_dir, "suppliers.csv"))}
    products = {r["product_id"]: r for r in _rows(os.path.join(data_dir, "products.csv"))}
    bom = {}
    for r in _rows(os.path.join(data_dir, "bom.csv")):
        bom.setdefault(r["product_id"], []).append(r)
    offers = {}
    by_slot = {}
    for r in _rows(os.path.join(data_dir, "component_offers.csv")):
        offers[r["offer_id"]] = r
        by_slot.setdefault((r["product_id"], r["slot"]), []).append(r)
    imports = {}
    imports_by_product = {}
    for r in _rows(os.path.join(data_dir, "finished_imports.csv")):
        imports[r["offer_id"]] = r
        imports_by_product.setdefault(r["product_id"], []).append(r)
    return dict(params=params, suppliers=suppliers, products=products, bom=bom,
                offers=offers, by_slot=by_slot, imports=imports,
                imports_by_product=imports_by_product)


class Rules:
    def __init__(self, inst, flags=()):
        self.inst = inst
        self.f = set(flags)
        p = inst["params"]
        year = int(p["delivery_calendar_year"])
        if "stale_threshold" in self.f:
            self.thr = 65
        else:
            self.thr = 60 if year < 2024 else (65 if year <= 2028 else 75)
        self.factor = 20 if ("factor20" in self.f or p["offeror_size"] != "small") else 30
        self.fallback_on = (p["evaluation_date"] < "2030-01-01") and "no_fallback" not in self.f
        self.notice = set(p.get("nonavailable_articles_available_domestically", []))

    # ---- piece level -------------------------------------------------
    def piece(self, o):
        """(outlay, cost_of_component, evaluated cost) for ONE piece, cents."""
        if o["supply_type"] == "in_house":
            d, oh, pr = _int(o["inhouse_direct_cents"]), _int(o["inhouse_overhead_cents"]), _int(o["inhouse_profit_cents"])
            cc = d + oh + (pr if "profit_in_cost" in self.f else 0)
            return d + oh, cc, d + oh
        price, frt, duty = _int(o["unit_price_cents"]), _int(o["freight_cents"]), _int(o["duty_cents"])
        cert = o["duty_free_certificate"] == "Y"
        outlay = price + frt + (0 if cert else duty)
        cc = price + frt + (0 if (cert and "cert_no_duty" in self.f) else duty)
        return outlay, cc, price + frt + duty

    def steel_foreign(self, o):
        melt, roll, coat = o["steel_melt_country"], o["steel_rolling_country"], o["steel_coating_country"]
        if "melt_only" in self.f:
            steps = [melt]
        elif "last_process" in self.f:
            steps = [coat if coat != "NONE" else roll]
        else:
            steps = [melt, roll] + ([] if coat == "NONE" else [coat])
        if "ore_matters" in self.f:
            steps.append(o["steel_ore_origin"])
        return any(s != "US" for s in steps)

    def comp_domestic(self, o):
        if "steel_is_component_origin" in self.f and _int(o["iron_steel_cost_cents"]) > 0:
            return not self.steel_foreign(o)
        org = o["component_origin"]
        if org == "US":
            return True
        if org == "UNKNOWN":
            return "unknown_domestic" in self.f
        if "ignore_list" in self.f:
            return False
        item = LISTED_CLASSES.get(o["material_class"])
        if item is None:
            return False
        if item in self.notice and "ignore_notice" not in self.f:
            return False
        return True

    # ---- build level -------------------------------------------------
    def us_build(self, pid, choice):
        """choice: dict slot -> offer row. Returns metrics dict."""
        prod = self.inst["products"][pid]
        outlay = ev = T = Dm = IS = FIS = 0
        sup = set()
        for b in self.inst["bom"][pid]:
            o = choice[b["slot"]]
            q = int(b["qty_per_unit"])
            po, pc, pe = self.piece(o)
            outlay += q * po
            ev += q * pe
            T += q * pc
            if self.comp_domestic(o):
                Dm += q * pc
            ist = _int(o["iron_steel_cost_cents"])
            if ist and (o["cots_fastener"] != "Y" or "count_fasteners" in self.f):
                IS += q * ist
                if self.steel_foreign(o):
                    FIS += q * ist
            sup.add(o["supplier_id"])
        asm = int(prod["assembly_cost_cents"])
        outlay += asm
        ev += asm
        if "assembly_in_cost" in self.f:
            T += asm
            Dm += asm
        cots = prod["cots_item"] == "Y"
        ns = "nonstrict" in self.f
        pred = (2 * IS >= T) if ns else (2 * IS > T)
        if cots and "cots_waives_steel" in self.f:
            track = "domestic_cots"
        elif pred:
            ok = (20 * FIS <= T) if ns else (20 * FIS < T)
            track = "domestic_iron_steel" if ok else "foreign"
        elif cots and "no_cots_waiver" not in self.f:
            track = "domestic_cots"
        else:
            ok = (100 * Dm >= self.thr * T) if ns else (100 * Dm > self.thr * T)
            track = "domestic_component_test" if ok else "foreign"
        fb = (not cots) and (not pred) and ((100 * Dm >= 55 * T) if ns else (100 * Dm > 55 * T))
        return dict(build="us", offers={s: o["offer_id"] for s, o in choice.items()},
                    unit_outlay=outlay, unit_eval=ev, cost_of_components=T,
                    domestic_component_cost=Dm, iron_steel_cost=IS,
                    foreign_iron_steel_cost=FIS, predominantly_iron_steel=pred,
                    track=track, fallback_eligible=fb, suppliers=sup)

    def import_build(self, r):
        c = _int(r["unit_price_cents"]) + _int(r["freight_cents"]) + _int(r["duty_cents"])
        return dict(build="import", import_offer=r["offer_id"], unit_outlay=c, unit_eval=c,
                    cost_of_components=None, domestic_component_cost=None, iron_steel_cost=None,
                    foreign_iron_steel_cost=None, predominantly_iron_steel=None,
                    track="foreign", fallback_eligible=False, suppliers={r["supplier_id"]},
                    dc_zero=True)

    def builds(self, pid):
        slots = [b["slot"] for b in self.inst["bom"][pid]]
        lists = [self.inst["by_slot"][(pid, s)] for s in slots]
        out = []
        for combo in itertools.product(*lists):
            out.append(self.us_build(pid, dict(zip(slots, combo))))
        for r in self.inst["imports_by_product"].get(pid, []):
            out.append(self.import_build(r))
        return out

    def admissibility(self, pid, blds):
        """Returns (status, info). status in domestic_required / fallback_required / foreign_allowed."""
        L = min(b["unit_eval"] for b in blds)
        low = [b for b in blds if b["unit_eval"] == L]
        dom = [b["unit_eval"] for b in blds if b["track"] != "foreign"]
        D = min(dom) if dom else None
        info = dict(low=L, lowest_domestic=D)
        if any(b["track"] != "foreign" for b in low):
            return "domestic_required", info
        E = Fraction(L * (100 + self.factor), 100)
        info["evaluated_low"] = E
        if D is not None:
            if ("tie_foreign" in self.f and D < E) or ("tie_foreign" not in self.f and D <= E):
                return "domestic_required", info
        if self.fallback_on and self.inst["products"][pid]["cots_item"] != "Y":
            def dc_le55(b):
                if b["build"] == "import":
                    return True
                T, Dm = b["cost_of_components"], b["domestic_component_cost"]
                return (100 * Dm < 55 * T) if "nonstrict" in self.f else (100 * Dm <= 55 * T)
            if all(dc_le55(b) for b in low):
                fbs = [b["unit_eval"] for b in blds if b["fallback_eligible"] and b["track"] == "foreign"]
                M = min(fbs) if fbs else None
                info["lowest_fallback"] = M
                if M is not None and M <= E:
                    return "fallback_required", info
        return "foreign_allowed", info


def allowed(status, b):
    if b["track"] != "foreign":
        return True
    if status == "foreign_allowed":
        return True
    if status == "fallback_required":
        return b["fallback_eligible"]
    return False


def optimize(inst, flags=(), budget_override=None, time_limit=120):
    R = Rules(inst, flags)
    sups = inst["suppliers"]
    unq = sorted(s for s, r in sups.items() if r["qualified"] != "Y")
    uidx = {s: i for i, s in enumerate(unq)}
    budget = int(inst["params"]["qualification_budget_cents"]) if budget_override is None else budget_override
    status = {}
    cols = []  # (pid, key, cost, build)
    base = 0
    for pid in sorted(inst["products"]):
        q = int(inst["products"][pid]["quantity"])
        blds = R.builds(pid)
        st, _ = R.admissibility(pid, blds)
        status[pid] = st
        best = {}
        for b in blds:
            if not allowed(st, b):
                continue
            key = frozenset(s for s in b["suppliers"] if s in uidx)
            c = q * b["unit_outlay"]
            if key not in best or c < best[key][0]:
                best[key] = (c, b)
        if not best:
            raise RuntimeError(f"no allowed build for {pid}")
        m = min(v[0] for v in best.values())
        base += m
        for key, (c, b) in best.items():
            cols.append((pid, key, c - m, b))
    nz, ny = len(cols), len(unq)
    n = nz + ny
    cvec = np.zeros(n)
    for j, (_, _, c, _) in enumerate(cols):
        cvec[j] = c
    for s, i in uidx.items():
        cvec[nz + i] = int(sups[s]["qualification_fee_cents"])
    A, lb, ub = [], [], []
    pids = sorted(inst["products"])
    for pid in pids:
        row = np.zeros(n)
        for j, col in enumerate(cols):
            if col[0] == pid:
                row[j] = 1
        A.append(row); lb.append(1); ub.append(1)
    for j, (_, key, _, _) in enumerate(cols):
        for s in key:
            row = np.zeros(n)
            row[j] = 1
            row[nz + uidx[s]] = -1
            A.append(row); lb.append(-np.inf); ub.append(0)
    row = np.zeros(n)
    for s, i in uidx.items():
        row[nz + i] = int(sups[s]["qualification_fee_cents"])
    A.append(row); lb.append(-np.inf); ub.append(budget)
    res = milp(cvec, constraints=LinearConstraint(np.array(A), lb, ub),
               integrality=np.ones(n), bounds=Bounds(0, 1),
               options={"mip_rel_gap": 0, "time_limit": time_limit})
    if res.status != 0:
        raise RuntimeError(f"milp status {res.status}: {res.message}")
    x = np.round(res.x).astype(int)
    plan = {}
    for j, (pid, key, c, b) in enumerate(cols):
        if x[j]:
            plan[pid] = b
    newq = sorted(s for s, i in uidx.items() if x[nz + i])
    # only keep qualifications actually used
    used = set().union(*[plan[p]["suppliers"] for p in plan])
    newq = [s for s in newq if s in used]
    fees = sum(int(sups[s]["qualification_fee_cents"]) for s in newq)
    total = sum(int(inst["products"][p]["quantity"]) * plan[p]["unit_outlay"] for p in plan) + fees
    return dict(plan=plan, status=status, new_qualifications=newq, qualification_spend=fees,
                total_outlay=total, rules=R)


def to_output(inst, sol):
    lines = []
    for pid in sorted(sol["plan"]):
        b = sol["plan"][pid]
        st = sol["status"][pid]
        basis = None
        if b["track"] == "foreign":
            basis = "fallback_55" if st == "fallback_required" else "unreasonable_cost"
        line = dict(product_id=pid, admissibility=st, build=b["build"],
                    offers=b.get("offers"), import_offer=b.get("import_offer"),
                    unit_outlay_cents=b["unit_outlay"],
                    cost_of_components_cents=b["cost_of_components"],
                    domestic_component_cost_cents=b["domestic_component_cost"],
                    iron_steel_cost_cents=b["iron_steel_cost"],
                    foreign_iron_steel_cost_cents=b["foreign_iron_steel_cost"],
                    track=b["track"], foreign_basis=basis)
        lines.append(line)
    return dict(total_outlay_cents=sol["total_outlay"],
                qualification_spend_cents=sol["qualification_spend"],
                new_qualifications=sol["new_qualifications"], lines=lines)
