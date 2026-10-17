"""Tests for the Buy American sourcing plan written to /app/output/plan.json."""
import json
import os

import pytest

from engine import STATUSES, Instance

PLAN = os.environ.get("PLAN_PATH", "/app/output/plan.json")
EXPECTED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected.json")

LINE_KEYS = {"product_id", "admissibility", "offers", "import_offer", "unit_outlay_cents",
             "cost_of_components_cents", "domestic_component_cost_cents", "iron_steel_cost_cents",
             "foreign_iron_steel_cost_cents", "specialty_metals_restricted", "specialty_metal_g",
             "noncompliant_specialty_metal_g"}


@pytest.fixture(scope="module")
def inst():
    return Instance()


@pytest.fixture(scope="module")
def plan():
    assert os.path.exists(PLAN), f"{PLAN} not found"
    with open(PLAN) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def lines(plan):
    return {l["product_id"]: l for l in plan["lines"]}


@pytest.fixture(scope="module")
def builds(inst, plan, lines):
    """Verifier's own metrics for the build each line names (None when the line is malformed)."""
    out = {}
    for pid, l in lines.items():
        try:
            if l["import_offer"] is not None:
                assert inst.imports[l["import_offer"]]["product_id"] == pid
                out[pid] = inst.import_metrics(l["import_offer"])
            else:
                out[pid] = inst.us_metrics(pid, l["offers"])
        except Exception:
            out[pid] = None
    return out


def test_plan_schema(plan):
    """plan.json has the top-level keys and one well-formed object per line, ordered by product_id."""
    assert set(plan) >= {"total_outlay_cents", "qualification_spend_cents", "new_qualifications", "lines"}
    assert plan["new_qualifications"] == sorted(plan["new_qualifications"])
    ids = [l["product_id"] for l in plan["lines"]]
    assert ids == sorted(ids)
    for l in plan["lines"]:
        assert set(l) == LINE_KEYS, l.get("product_id")
        assert l["admissibility"] in STATUSES
        assert isinstance(l["specialty_metals_restricted"], bool)


def test_every_product_has_one_valid_build(inst, lines):
    """Each product appears once and names either one offer for every BOM slot or one of its finished imports."""
    assert set(lines) == set(inst.products)
    for pid, l in lines.items():
        if l["import_offer"] is not None:
            assert l["offers"] is None, pid
            assert l["import_offer"] in inst.product_imports.get(pid, []), pid
        else:
            assert isinstance(l["offers"], dict), pid
            assert set(l["offers"]) == {s for s, _ in inst.slots[pid]}, pid
            for slot, oid in l["offers"].items():
                assert oid in inst.slot_offers[(pid, slot)], (pid, slot, oid)


def test_line_figures_match_recomputation(builds, lines):
    """Unit outlay, cost of components, domestic component cost, iron/steel and specialty metal figures equal the verifier's."""
    keys = [("unit_outlay_cents", "unit_outlay"), ("cost_of_components_cents", "cost_of_components"),
            ("domestic_component_cost_cents", "domestic_component_cost"), ("iron_steel_cost_cents", "iron_steel_cost"),
            ("foreign_iron_steel_cost_cents", "foreign_iron_steel_cost"),
            ("specialty_metals_restricted", "restricted"), ("specialty_metal_g", "specialty_metal_g"),
            ("noncompliant_specialty_metal_g", "noncompliant_specialty_metal_g")]
    bad = []
    for pid, l in lines.items():
        b = builds[pid]
        assert b is not None, pid
        for k, v in keys:
            if l[k] != b[v]:
                bad.append((pid, k, l[k], b[v]))
    assert not bad, bad[:10]


def test_specialty_metals_compliance(builds):
    """Every line for a covered item meets the DFARS specialty metals restriction."""
    bad = [pid for pid, b in builds.items() if b is not None and not b["acceptable"]]
    assert all(b is not None for b in builds.values())
    assert not bad, bad


def test_admissibility_matches_dfars_evaluation(inst, lines):
    """Each product's Buy American evaluation outcome (domestic required or foreign allowed) is correct."""
    bad = [(pid, l["admissibility"], inst.status(pid)) for pid, l in lines.items() if l["admissibility"] != inst.status(pid)]
    assert not bad, bad


def test_every_line_is_deliverable(inst, builds):
    """No line delivers a non-domestic end product unless the evaluation allows it, nor an offer that may not be considered."""
    bad = []
    for pid, b in builds.items():
        assert b is not None, pid
        st = inst.status(pid)
        if not b.get("considered", True) or not (b["domestic"] or st == "foreign_allowed"):
            bad.append((pid, st, b["track"]))
    assert not bad, bad


def test_suppliers_qualified_within_budget(inst, plan, builds):
    """Every supplier used is already qualified or listed as a new qualification, and audit fees fit the budget."""
    used = set().union(*[b["suppliers"] for b in builds.values() if b is not None])
    newq = set(plan["new_qualifications"])
    for s in newq:
        assert s in inst.suppliers and inst.suppliers[s]["qualified"] != "Y", s
    missing = [s for s in used if inst.suppliers[s]["qualified"] != "Y" and s not in newq]
    assert not missing, missing
    spend = sum(int(inst.suppliers[s]["qualification_fee_cents"]) for s in newq)
    assert plan["qualification_spend_cents"] == spend
    assert spend <= inst.budget


def test_total_outlay_matches_plan(inst, plan, builds):
    """total_outlay_cents equals quantity times unit outlay summed over lines, plus qualification fees."""
    assert all(b is not None for b in builds.values())
    total = sum(int(inst.products[p]["quantity"]) * b["unit_outlay"] for p, b in builds.items())
    total += sum(int(inst.suppliers[s]["qualification_fee_cents"]) for s in plan["new_qualifications"])
    assert plan["total_outlay_cents"] == total


def test_total_outlay_is_minimum(inst, plan):
    """The plan's total outlay equals the minimum achievable under the rules (any optimal plan is accepted)."""
    best = inst.optimum()
    with open(EXPECTED) as f:
        assert json.load(f)["total_outlay_cents"] == best
    assert plan["total_outlay_cents"] == best, (plan["total_outlay_cents"], best)
