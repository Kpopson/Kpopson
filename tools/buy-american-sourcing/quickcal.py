"""Quick whole-instance check: optimal plan under each shortcut, graded by the true rules."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bacore
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "../../tasks/buy-american-sourcing/tests/data")
inst = bacore.load(d)
truth = bacore.optimize(inst)
T = bacore.Rules(inst)
print("truth", truth["total_outlay"])
for fl in bacore.SHORTCUTS:
    note = ""
    try:
        s = bacore.optimize(inst, (fl,))
    except Exception as e:
        s = bacore.optimize(inst, (fl,), budget_override=10**12); note = " (infeasible within budget)"
    bad = []
    for pid, b in s["plan"].items():
        blds = T.builds(pid)
        st, _ = T.admissibility(pid, blds)
        tb = next(x for x in blds if (x["build"] == b["build"]) and (x.get("offers") == b.get("offers")) and (x.get("import_offer") == b.get("import_offer")))
        if not bacore.allowed(st, tb):
            bad.append(pid)
    stat = sum(1 for p in s["status"] if s["status"][p] != truth["status"][p])
    print(f"{fl:28s} illegal={len(bad):2d} status_diff={stat:2d} outlay_delta={s['total_outlay']-truth['total_outlay']:>10d}{note}")
