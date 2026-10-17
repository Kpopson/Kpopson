"""Tests for the Buy American sourcing plan written to /app/output/plan.json."""
import json
import os

import pytest

from engine import STATUSES, TRACKS, Instance

PLAN = os.environ.get("PLAN_PATH", "/app/output/plan.json")
EXPECTED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected.json")

LINE_KEYS = {"product_id", "admissibility", "build", "offers", "import_offer", "unit_outlay_cents",
             "cost_of_components_cents", "domestic_component_cost_cents", "iron_steel_cost_cents",
             "foreign_iron_steel_cost_cents", "track", "foreign_basis"}


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
            if l["build"] == "import":
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
    assert isinstance(plan["total_outlay_cents"], int) and isinstance(plan["qualification_spend_cents"], int)
    assert plan["new_qualifications"] == sorted(plan["new_qualifications"])
    ids = [l["product_id"] for l in plan["lines"]]
    assert ids == sorted(ids)
    for l in plan["lines"]:
        assert set(l) == LINE_KEYS, l.get("product_id")
        assert l["admissibility"] in STATUSES and l["track"] in TRACKS
        assert l["build"] in ("us", "import")
        assert l["foreign_basis"] in (None, "unreasonable_cost", "fallback_25_106_b2")


def test_every_product_has_one_valid_build(inst, lines):
    """Each product appears once and names either one offer for every BOM slot or one of its finished imports."""
    assert set(lines) == set(inst.products)
    for pid, l in lines.items():
        if l["build"] == "import":
            assert l["offers"] is None
            assert l["import_offer"] in inst.product_imports.get(pid, []), pid
        else:
            assert l["import_offer"] is None
            assert set(l["offers"]) == {s for s, _ in inst.slots[pid]}, pid
            for slot, oid in l["offers"].items():
                assert oid in inst.slot_offers[(pid, slot)], (pid, slot, oid)


def test_line_figures_match_recomputation(builds, lines):
    """Unit outlay, cost of components, domestic component cost and iron/steel figures equal the verifier's."""
    keys = [("unit_outlay_cents", "unit_outlay"), ("cost_of_components_cents", "cost_of_components"),
            ("domestic_component_cost_cents", "domestic_component_cost"), ("iron_steel_cost_cents", "iron_steel_cost"),
            ("foreign_iron_steel_cost_cents", "foreign_iron_steel_cost")]
    bad = []
    for pid, l in lines.items():
        b = builds[pid]
        assert b is not None, pid
        for k, v in keys:
            if l[k] != b[v]:
                bad.append((pid, k, l[k], b[v]))
    assert not bad, bad[:10]


def test_admissibility_matches_far_evaluation(inst, lines):
    """Each product's Buy American evaluation outcome (domestic required, 55% fallback, or foreign allowed) is correct."""
    bad = [(pid, l["admissibility"], inst.status(pid)) for pid, l in lines.items() if l["admissibility"] != inst.status(pid)]
    assert not bad, bad


def test_every_line_is_deliverable(inst, builds):
    """No line delivers a foreign end product unless the evaluation allows it (or it is a qualifying >55% fallback build)."""
    bad = []
    for pid, b in builds.items():
        assert b is not None, pid
        st = inst.status(pid)
        if not inst.deliverable(st, b):
            bad.append((pid, st, b["track"]))
    assert not bad, bad


def test_track_and_basis_are_consistent(inst, builds, lines):
    """The reported track is the one the build's own figures satisfy, and foreign lines carry the right basis."""
    bad = []
    for pid, l in lines.items():
        b = builds[pid]
        assert b is not None, pid
        if l["track"] != b["track"]:
            bad.append((pid, "track", l["track"], b["track"]))
        want = None
        if b["track"] == "foreign":
            want = "fallback_25_106_b2" if inst.status(pid) == "fallback_required" else "unreasonable_cost"
        if l["foreign_basis"] != want:
            bad.append((pid, "basis", l["foreign_basis"], want))
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
    best, _ = inst.optimum()
    with open(EXPECTED) as f:
        assert json.load(f)["total_outlay_cents"] == best
    assert plan["total_outlay_cents"] == best, (plan["total_outlay_cents"], best)
