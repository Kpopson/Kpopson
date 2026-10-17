"""Cross-check reference solution (CP-SAT) against the verifier engine (enumeration + HiGHS)
on many seeds (dev only).  usage: python3 crosscheck.py [N] [START]"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.join(HERE, "..", "..", "tasks", "buy-american-sourcing")
PY = sys.executable


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    mism = 0
    for seed in range(start, start + n):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([PY, os.path.join(HERE, "generate.py"), "--seed", str(seed), "--out", d, "--quiet"], check=True)
            out = os.path.join(d, "out")
            subprocess.run([PY, os.path.join(TASK, "solution", "solve.py")], check=True, capture_output=True,
                           env=dict(os.environ, DATA_DIR=os.path.join(d, "tests", "data"), OUTPUT_DIR=out))
            plan = json.load(open(os.path.join(out, "plan.json")))
            code = ("import sys,json; sys.path.insert(0, %r); import engine; i=engine.Instance(); b,s=i.optimum();"
                    "print(json.dumps([b,s]))" % os.path.join(TASK, "tests"))
            r = subprocess.run([PY, "-c", code], check=True, capture_output=True, text=True,
                               env=dict(os.environ, VERIFIER_DATA_DIR=os.path.join(d, "tests", "data")))
            best, st = json.loads(r.stdout)
            exp = json.load(open(os.path.join(d, "tests", "expected.json")))
            sd = sum(1 for l in plan["lines"] if l["admissibility"] != st[l["product_id"]])
            bad = plan["total_outlay_cents"] != best or best != exp["total_outlay_cents"] or sd
            mism += bool(bad)
            binding = exp["unbudgeted_total_outlay_cents"] < best
            print(f"seed {seed}: oracle {plan['total_outlay_cents']} verifier {best} dev {exp['total_outlay_cents']} "
                  f"status_diff {sd} new_quals {len(plan['new_qualifications'])} budget_binding {binding}"
                  + ("  <-- MISMATCH" if bad else ""), flush=True)
    print(f"{mism} mismatches in {n} seeds")


if __name__ == "__main__":
    main()
