# buy-american-sourcing dev tools (never upload)

These files build and calibrate `tasks/buy-american-sourcing`. They must not be
uploaded with the task: they contain the generator and the secret seed.

| file | what it does |
|------|--------------|
| `bacore.py` | Rules engine (FAR 25.101, 25.106, 25.502, 52.225-1 Oct 2022) with shortcut flags for wrong readings |
| `generate.py` | Seeded generator. Writes identical inputs to `environment/data` and `tests/data`, and `tests/expected.json` |
| `quickcal.py` | Whole-instance effect of each shortcut (illegal lines, outlay change) |
| `calibrate.py` | Grades each shortcut's optimal plan with the real tests. Every shortcut must fail a core test |
| `crosscheck.py` | Reference solution (CP-SAT) vs verifier engine (enumeration + HiGHS) on many seeds |

Regenerate the shipped instance (secret seed is the default in `generate.py`):

    python3 tools/buy-american-sourcing/generate.py
    python3 tools/buy-american-sourcing/calibrate.py
    python3 tools/buy-american-sourcing/crosscheck.py 100 1000

Needs `ortools==9.15.6755 scipy==1.18.1 numpy==2.5.3 pytest==9.1.1`.

Rule sources: GSA FAR DITA files (github.com/GSA/GSA-Acquisition-FAR, through FAC 2025-06):
25.101, 25.103, 25.104, 25.105, 25.106, 25.502, 25.504-1, 52.225-1.

Planted readings (each has at least one product where it changes the answer):
nonstrict thresholds, 65% for a 2029 delivery, unknown origin as domestic, duty dropped
under a duty-free certificate, ignoring the 25.104 list, applying the list to the article the
solicitation says is available, no COTS waiver, COTS waiver covering iron/steel products,
counting COTS fasteners, steel origin by melt only, by last process, by ore, steel origin used
as component origin, 20% factor, tie to foreign, no 55% fallback, profit in in-house cost,
assembly in cost of components, budget-blind plan.
