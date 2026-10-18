"""Grade each shortcut's optimal plan with the real tests (dev only).

usage: python3 calibrate.py [--task TASKDIR]
For every shortcut in bacore.SHORTCUTS (plus budget-blind and approved-vendors-only
plans) this writes the plan the shortcut believes is optimal, runs
tests/test_outputs.py against it, and lists the failing tests.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bacore  # noqa: E402

CORE = {"test_admissibility_matches_dfars_evaluation", "test_every_line_is_deliverable", "test_magnet_restriction",
        "test_specialty_metals_compliance", "test_suppliers_qualified_within_budget", "test_total_outlay_is_minimum"}


def run_tests(task, plan):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "plan.json")
        if plan is not None:
            json.dump(plan, open(p, "w"))
        env = dict(os.environ, PLAN_PATH=p)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider",
                            os.path.join(task, "tests", "test_outputs.py")],
                           capture_output=True, text=True, env=env, cwd=os.path.join(task, "tests"))
        failed = sorted({ln.split("::")[1].split(" ")[0] for ln in r.stdout.splitlines()
                         if (ln.startswith("FAILED") or ln.startswith("ERROR")) and "::" in ln})
        return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=os.path.join(os.path.dirname(__file__), "..", "..", "tasks", "buy-american-sourcing"))
    a = ap.parse_args()
    inst = bacore.load(os.path.join(a.task, "tests", "data"))
    ok = True
    sol = bacore.optimize(inst)
    f = run_tests(a.task, bacore.to_output(inst, sol))
    print(f"{'oracle-equivalent':28s} failed={f}")
    ok &= not f
    f = run_tests(a.task, None)
    print(f"{'nop':28s} failed={len(f)} tests")
    ok &= len(f) > 0
    cases = [(fl, (fl,), None) for fl in bacore.SHORTCUTS] + [("budget_blind", (), 10 ** 12)]
    for name, flags, bud in cases:
        note = ""
        try:
            s = bacore.optimize(inst, flags, budget_override=bud)
        except RuntimeError:
            s = bacore.optimize(inst, flags, budget_override=10 ** 12)
            note = " (shortcut infeasible in budget; graded its unbudgeted plan)"
        failed = run_tests(a.task, bacore.to_output(inst, s))
        core = sorted(set(failed) & CORE)
        print(f"{name:28s} core_failed={core} other={sorted(set(failed) - CORE)}{note}")
        ok &= bool(core)
    print("ALL SHORTCUTS FAIL A CORE TEST" if ok else "CALIBRATION PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
