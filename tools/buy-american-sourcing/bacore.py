"""Development rules engine for the buy-american-sourcing task (DoD version). Never uploaded.

Applies, the way the task grades them:
  DFARS 252.225-7001 (FEB 2024) Buy American and Balance of Payments Program, Basic
  DFARS 252.225-7009 (JAN 2023) specialty metals, with 225.7003-1/-2/-3
  DFARS 225.502(c)(ii) evaluation with the 225.106 50% factor, 225.872-1 qualifying countries
  FAR 25.104 nonavailable list, FAR 25.502(d)(1) ties
SHORTCUTS reproduce plausible wrong readings for calibrate.py.

Optimizer: enumerate every build of every product, filter in exact integer arithmetic,
collapse builds needing the same set of unqualified vendors, solve a selection MILP (HiGHS).
"""
import csv
import itertools
import json
import os
from fractions import Fraction

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

QC = {"AU", "AT", "BE", "CA", "CZ", "DK", "EG", "EE", "FI", "FR", "DE", "GR", "IL", "IT", "JP", "LV",
      "LT", "LU", "NL", "NO", "PL", "PT", "SI", "ES", "SE", "CH", "TR", "GB"}
CASE_BY_CASE = {"AT"}  # 225.872-1(b): Austria only purchase-by-purchase

LISTED_CLASSES = {
    "hog bristles": "Hog bristles for brushes",
    "natural rubber, crude": "Rubber, crude and latex (natural)",
    "quartz crystals": "Quartz crystals",
    "cover glass, microscope slide": "Cover glass, microscope slide",
}

# next higher assembly -> covered by 225.7003-2(a)(1)?
RESTRICTED_USE = {
    "M1083A1 FMTV 5-ton cargo truck": True,
    "M1151A1 HMMWV armament carrier": True,
    "M1126 Stryker infantry carrier vehicle": True,
    "M2A1 .50 caliber machine gun (crew-served weapon)": True,
    "M240B 7.62 mm machine gun (crew-served weapon)": True,
    "10K all-terrain lifter, army system (ATLAS forklift)": False,
    "MB-4 aircraft tow tractor (aircraft ground support equipment)": False,
    "Commercial 3/4-ton pickup truck, base motor pool (COTS vehicle)": False,
    "Warehouse and facility use": False,
}

SM_FORMS_NOT_COTS_EXCEPTED = {"mill_product", "forging", "casting", "magnet", "fastener"}

SHORTCUTS = {
    # FAR-level
    "nonstrict": "uses >= / <= where the clauses say exceeds / less than",
    "stale_threshold": "uses 65% for a 2029 delivery",
    "unknown_domestic": "treats components of unknown origin as domestic",
    "cert_no_duty": "drops duty from cost of components under a duty-free entry certificate",
    "ignore_list": "ignores the FAR 25.104 nonavailable list",
    "ignore_notice": "applies the list to the article the solicitation says is available",
    "no_cots_waiver": "applies the component test to COTS end products",
    "cots_waives_steel": "lets the COTS waiver cover predominantly iron/steel products",
    "count_fasteners": "counts COTS fasteners in iron and steel content",
    "profit_in_cost": "includes in-house profit in cost of components",
    "assembly_in_cost": "adds assembly cost to cost of components (as domestic)",
    "tie_foreign": "awards the foreign build when evaluated price ties",
    # DFARS Buy American
    "qc_not_domestic": "does not count qualifying country components or steel as domestic (FAR reading)",
    "korea_qc": "treats South Korea as a qualifying country",
    "factor30": "uses the FAR 30% small business factor instead of DFARS 50%",
    "qc_considered": "considers qualifying country end products in a small business set-aside (225.872-3(a))",
    # specialty metals
    "sm_ignore": "ignores the specialty metals restriction",
    "sm_everywhere": "applies the specialty metals restriction to every product",
    "sm_nonstrict_comp": "classifies steel at exactly the limit as specialty metal",
    "sm_hsla": "treats microalloyed HSLA steel as specialty metal",
    "sm_mn_ignore": "ignores the manganese limit when classifying steel",
    "sm_all_processes": "requires rolling and coating, not just melting, in the US or a qualifying country",
    "sm_no_qc_mfg": "ignores the exception for items manufactured in a qualifying country",
    "sm_cost_basis": "measures the 2% minimal content by cost instead of weight",
    "sm_magnet_2pct": "lets noncompliant magnets use the 2% minimal content exception",
    "sm_cots_all": "applies the COTS exception to COTS mill products, forgings and fasteners",
    "sm_no_fastener_cert": "ignores the 50% fastener manufacturer exception",
    "sm_strict_2pct": "requires noncompliant content strictly below 2%",
    "sm_no_elim": "does not drop specialty-metal-noncompliant builds before the price evaluation",
    "sm_electronic_restricted": "applies the restriction to electronic components",
}
# not a calibrated shortcut: the generator rejects any product where the FAR 25.106(b)(2) fallback would matter
GUARD_FLAGS = {"far_fallback"}

TRACKS = ("domestic_component_test", "domestic_iron_steel", "domestic_cots", "qualifying_country", "foreign")


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _int(v):
    return int(v) if v not in ("", None) else 0


def _dec(v):
    return Fraction(v) if v not in ("", None) else Fraction(0)


def load(data_dir):
    j = lambda n: os.path.join(data_dir, n)
    params = json.load(open(j("params.json")))
    bom = {}
    for r in _rows(j("bom.csv")):
        bom.setdefault(r["product_id"], []).append(r)
    by_slot = {}
    offers = {}
    for r in _rows(j("component_offers.csv")):
        offers[r["offer_id"]] = r
        by_slot.setdefault((r["product_id"], r["slot"]), []).append(r)
    imports, imports_by_product = {}, {}
    for r in _rows(j("finished_imports.csv")):
        imports[r["offer_id"]] = r
        imports_by_product.setdefault(r["product_id"], []).append(r)
    return dict(params=params, suppliers={r["supplier_id"]: r for r in _rows(j("suppliers.csv"))},
                products={r["product_id"]: r for r in _rows(j("products.csv"))},
                materials={r["material_id"]: r for r in _rows(j("materials.csv"))},
                bom=bom, offers=offers, by_slot=by_slot, imports=imports, imports_by_product=imports_by_product)


class Rules:
    def __init__(self, inst, flags=()):
        self.inst = inst
        self.f = set(flags)
        p = inst["params"]
        year = int(p["delivery_calendar_year"])
        self.thr = 65 if "stale_threshold" in self.f else (60 if year < 2024 else (65 if year <= 2028 else 75))
        self.factor = 30 if "factor30" in self.f else 50
        self.notice = set(p.get("nonavailable_articles_available_domestically", []))
        self.qc = set() if "qc_not_domestic" in self.f else set(QC)
        if "korea_qc" in self.f:
            self.qc.add("KR")
        self.sm_qc = set(QC) | ({"KR"} if "korea_qc" in self.f else set())
        self.case_by_case = set() if "austria_exempt" in self.f else set(CASE_BY_CASE)
        self.case_by_case -= {c for c in p.get("public_interest_determinations", [])}
        self._sm_cache = {}
        self.setaside = bool(p.get("small_business_set_aside")) and "qc_considered" not in self.f

    def ok_country(self, c):
        return c == "US" or c in self.qc

    # ---------------- specialty metal classification ----------------
    def is_sm(self, mid):
        if not mid:
            return False
        if mid in self._sm_cache:
            return self._sm_cache[mid]
        m = self.inst["materials"][mid]
        base = m["base_metal"]
        el = {k[4:]: _dec(v) for k, v in m.items() if k.startswith("max_")}
        gt = (lambda a, b: a >= b) if "sm_nonstrict_comp" in self.f else (lambda a, b: a > b)
        if base == "iron":
            if "sm_hsla" in self.f and (el.get("nb", 0) > 0 or el.get("v", 0) > 0):
                r = True
            else:
                lim = [("si", Fraction("0.60")), ("cu", Fraction("0.60"))]
                if "sm_mn_ignore" not in self.f:
                    lim.append(("mn", Fraction("1.65")))
                r = any(gt(el.get(e, 0), v) for e, v in lim) or any(
                    gt(el.get(e, 0), Fraction("0.25")) for e in ("al", "cr", "co", "mo", "ni", "nb", "ti", "w", "v"))
        elif base in ("titanium", "zirconium"):
            r = True
        elif base in ("nickel", "cobalt"):
            other = sum(v for e, v in el.items() if e not in (("ni", "fe") if base == "nickel" else ("co", "fe")))
            r = other > 10
        else:
            r = False
        self._sm_cache[mid] = r
        return r

    def restricted(self, pid):
        if "sm_ignore" in self.f:
            return False
        if "sm_everywhere" in self.f:
            return True
        return RESTRICTED_USE[self.inst["products"][pid]["next_higher_assembly"]]

    # ---------------- piece level ----------------
    def piece(self, o):
        if o["supply_type"] == "in_house":
            d, oh, pr = _int(o["inhouse_direct_cents"]), _int(o["inhouse_overhead_cents"]), _int(o["inhouse_profit_cents"])
            return d + oh, d + oh + (pr if "profit_in_cost" in self.f else 0), d + oh
        price, frt, duty = _int(o["unit_price_cents"]), _int(o["freight_cents"]), _int(o["duty_cents"])
        cert = o["duty_free_certificate"] == "Y"
        return (price + frt + (0 if cert else duty),
                price + frt + (0 if (cert and "cert_no_duty" in self.f) else duty),
                price + frt + duty)

    def steel_foreign(self, o):
        steps = [o["metal_melt_country"], o["metal_rolling_country"]]
        if o["metal_coating_country"] != "NONE":
            steps.append(o["metal_coating_country"])
        if "ore_matters" in self.f:
            steps.append(o["metal_ore_origin"])
        return not all(self.ok_country(s) for s in steps)

    def comp_domestic(self, o):
        org = o["component_origin"]
        if org == "UNKNOWN":
            return "unknown_domestic" in self.f
        if self.ok_country(org):
            return True
        if "ignore_list" in self.f:
            return False
        item = LISTED_CLASSES.get(o["material_class"])
        if item is None:
            return False
        return not (item in self.notice and "ignore_notice" not in self.f)

    def sm_piece(self, o, pc):
        """(sm_weight, noncompliant_weight, noncompliant_magnet) for one piece; pc = piece cost for cost basis."""
        if not self.is_sm(o["metal_material"]):
            return 0, 0, False
        w = pc if "sm_cost_basis" in self.f else _int(o["metal_g_per_piece"])
        form = o["part_form"]
        if form == "electronic" and "sm_electronic_restricted" not in self.f:
            return w, 0, False
        if o["component_origin"] in QC and "sm_no_qc_mfg" not in self.f:
            return w, 0, False
        if o["component_cots"] == "Y" and (form not in SM_FORMS_NOT_COTS_EXCEPTED or "sm_cots_all" in self.f):
            return w, 0, False
        if form == "fastener" and o["fastener_mfr_dod_certified"] == "Y" and "sm_no_fastener_cert" not in self.f:
            return w, 0, False
        melt_ok = o["metal_melt_country"] == "US" or o["metal_melt_country"] in self.sm_qc
        if "sm_all_processes" in self.f:
            for c in (o["metal_rolling_country"], o["metal_coating_country"]):
                if c not in ("NONE", "US") and c not in self.sm_qc:
                    melt_ok = False
        if melt_ok:
            return w, 0, False
        if form == "magnet" and "sm_magnet_2pct" not in self.f:
            return w, 0, True
        return w, w, False

    def sm_ok(self, total, bad, magnet_bad):
        if magnet_bad:
            return False
        return (100 * bad < 2 * total) if "sm_strict_2pct" in self.f else (100 * bad <= 2 * total)

    # ---------------- builds ----------------
    def us_build(self, pid, choice):
        prod = self.inst["products"][pid]
        outlay = ev = T = Dm = IS = FIS = SMT = SMB = 0
        mag = False
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
            w, bad, m = self.sm_piece(o, pc)
            SMT += q * w
            SMB += q * bad
            mag = mag or m
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
            track = "domestic_iron_steel" if ((20 * FIS <= T) if ns else (20 * FIS < T)) else "foreign"
        elif cots and "no_cots_waiver" not in self.f:
            track = "domestic_cots"
        else:
            track = "domestic_component_test" if ((100 * Dm >= self.thr * T) if ns else (100 * Dm > self.thr * T)) else "foreign"
        rest = self.restricted(pid)
        fb = (not cots) and (not pred) and 100 * Dm > 55 * T
        return dict(build="us", fallback_ok=fb, dc_le55=100 * Dm <= 55 * T, offers={s: o["offer_id"] for s, o in choice.items()}, unit_outlay=outlay,
                    unit_eval=ev, cost_of_components=T, domestic_component_cost=Dm, iron_steel_cost=IS,
                    foreign_iron_steel_cost=FIS, track=track, domestic=track != "foreign", exempt=False,
                    restricted=rest, sm_total=SMT if rest else None, sm_bad=SMB if rest else None,
                    sm_ok=(not rest) or self.sm_ok(SMT, SMB, mag), suppliers=sup)

    def import_build(self, r):
        pid = r["product_id"]
        c = _int(r["unit_price_cents"]) + _int(r["freight_cents"]) + _int(r["duty_cents"])
        country = r["country_of_manufacture"]
        T, UQ = _int(r["cost_of_components_cents"]), _int(r["us_qc_component_cost_cents"])
        IS, NIS = _int(r["iron_steel_cost_cents"]), _int(r["non_us_qc_iron_steel_cost_cents"])
        cots = self.inst["products"][pid]["cots_item"] == "Y"
        ns = "nonstrict" in self.f
        qc_country = country in self.qc
        qcep = qc_country and (cots or ((100 * UQ >= self.thr * T) if ns else (100 * UQ > self.thr * T)))
        pred = (2 * IS >= T) if ns else (2 * IS > T)
        steel_ok = (not pred) or "qc_import_no_steel_test" in self.f or ((20 * NIS <= T) if ns else (20 * NIS < T))
        exempt = qcep and country not in self.case_by_case and steel_ok
        rest = self.restricted(pid)
        smt, smb = _int(r["specialty_metal_g"]), _int(r["noncompliant_specialty_metal_g"])
        if country in QC and "sm_no_qc_mfg" not in self.f:
            smb = 0
        return dict(build="import", considered=not (self.setaside and qcep),
                    fallback_ok=False, dc_le55=100 * UQ <= 55 * T, import_offer=r["offer_id"], unit_outlay=c, unit_eval=c,
                    cost_of_components=None, domestic_component_cost=None, iron_steel_cost=None,
                    foreign_iron_steel_cost=None, track="qualifying_country" if qcep else "foreign",
                    domestic=False, exempt=exempt, restricted=rest, sm_total=smt if rest else None,
                    sm_bad=smb if rest else None, sm_ok=(not rest) or self.sm_ok(smt, smb, False),
                    suppliers={r["supplier_id"]})

    def builds(self, pid):
        slots = [b["slot"] for b in self.inst["bom"][pid]]
        out = [self.us_build(pid, dict(zip(slots, combo)))
               for combo in itertools.product(*[self.inst["by_slot"][(pid, s)] for s in slots])]
        out += [self.import_build(r) for r in self.inst["imports_by_product"].get(pid, [])]
        return out

    def admissibility(self, pid, blds):
        """DFARS 225.502(c)(ii), price the determining factor. Returns (status, info)."""
        blds = [b for b in blds if b.get("considered", True)]       # 225.872-3(a)
        acc = blds if "sm_no_elim" in self.f else [b for b in blds if b["sm_ok"]]
        if not acc:
            return "domestic_required", dict(low=None, lowest_domestic=None)
        L = min(b["unit_eval"] for b in acc)
        low = [b for b in acc if b["unit_eval"] == L]
        dom = [b["unit_eval"] for b in acc if b["domestic"]]
        info = dict(low=L, lowest_domestic=min(dom) if dom else None)
        if any(b["domestic"] for b in low):
            return "domestic_required", info                      # (A)
        if not dom:
            return "foreign_allowed", info                        # (B)
        D = min(dom)
        if any(b["exempt"] for b in low):
            return "foreign_allowed", info                        # (C)
        if "no_rule_d" not in self.f and any(b["exempt"] and b["unit_eval"] < D for b in acc):
            return "foreign_allowed", info                        # (D)
        E = Fraction(L * (100 + self.factor), 100)                # (E)
        info["evaluated_low"] = E
        if D < E or (D == E and "tie_foreign" not in self.f):
            return "domestic_required", info
        if "far_fallback" in self.f and self.inst["products"][pid]["cots_item"] != "Y" and all(b["dc_le55"] for b in low):
            if any(b["fallback_ok"] and b["unit_eval"] <= E for b in acc):
                return "fallback_required", info
        return "foreign_allowed", info


def allowed(status, b):
    if not b["sm_ok"] or not b.get("considered", True):
        return False
    if status == "fallback_required":
        return b["domestic"] or b["fallback_ok"]
    return b["domestic"] or status == "foreign_allowed"


def optimize(inst, flags=(), budget_override=None, time_limit=120, fees_only=False):
    R = Rules(inst, flags)
    sups = inst["suppliers"]
    unq = sorted(s for s, r in sups.items() if r["qualified"] != "Y")
    uidx = {s: i for i, s in enumerate(unq)}
    budget = int(inst["params"]["qualification_budget_cents"]) if budget_override is None else budget_override
    status, cols = {}, []
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
        cols += [(pid, key, c - m, b) for key, (c, b) in best.items()]
    nz, n = len(cols), len(cols) + len(unq)
    fee = np.array([int(sups[s]["qualification_fee_cents"]) for s in unq], dtype=float)
    cvec = np.concatenate([np.array([0 if fees_only else col[2] for col in cols], dtype=float), fee])
    A, lb, ub = [], [], []
    for pid in sorted(inst["products"]):
        row = np.zeros(n)
        row[[j for j, col in enumerate(cols) if col[0] == pid]] = 1
        A.append(row); lb.append(1); ub.append(1)
    for j, (_, key, _, _) in enumerate(cols):
        for s in key:
            row = np.zeros(n)
            row[j], row[nz + uidx[s]] = 1, -1
            A.append(row); lb.append(-np.inf); ub.append(0)
    row = np.zeros(n)
    row[nz:] = fee
    A.append(row); lb.append(-np.inf); ub.append(budget)
    res = milp(cvec, constraints=LinearConstraint(np.array(A), lb, ub), integrality=np.ones(n),
               bounds=Bounds(0, 1), options={"mip_rel_gap": 0, "time_limit": time_limit})
    if res.status != 0:
        raise RuntimeError(f"milp status {res.status}: {res.message}")
    x = np.round(res.x).astype(int)
    plan = {cols[j][0]: cols[j][3] for j in range(nz) if x[j]}
    used = set().union(*[b["suppliers"] for b in plan.values()])
    newq = [s for s in unq if x[nz + uidx[s]] and s in used]
    fees = sum(int(sups[s]["qualification_fee_cents"]) for s in newq)
    total = sum(int(inst["products"][p]["quantity"]) * b["unit_outlay"] for p, b in plan.items()) + fees
    return dict(plan=plan, status=status, new_qualifications=newq, qualification_spend=fees,
                total_outlay=total, rules=R)


def to_output(inst, sol):
    lines = []
    for pid in sorted(sol["plan"]):
        b = sol["plan"][pid]
        lines.append(dict(product_id=pid, admissibility=sol["status"][pid], build=b["build"],
                          offers=b.get("offers"), import_offer=b.get("import_offer"),
                          unit_outlay_cents=b["unit_outlay"], cost_of_components_cents=b["cost_of_components"],
                          domestic_component_cost_cents=b["domestic_component_cost"],
                          iron_steel_cost_cents=b["iron_steel_cost"],
                          foreign_iron_steel_cost_cents=b["foreign_iron_steel_cost"], track=b["track"],
                          specialty_metals_restricted=b["restricted"], specialty_metal_g=b["sm_total"],
                          noncompliant_specialty_metal_g=b["sm_bad"]))
    return dict(total_outlay_cents=sol["total_outlay"], qualification_spend_cents=sol["qualification_spend"],
                new_qualifications=sol["new_qualifications"], lines=lines)
