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

Rule sources (DoD version): DFARS 252.225-7001 (Basic, FEB 2024), 252.225-7009 (JAN 2023),
225.7003-1/-2/-3, 225.502(c), 225.106, 225.103, 225.872-1 (pasted from Cornell LII), 225.872-3(a) (quoted by the deep review), and the GSA FAR
DITA files for FAR 25.104 and 25.502(d).

Planted readings: all keys of bacore.SHORTCUTS (35, incl. sub-assembly and set-aside readings), plus a budget-blind plan. The generator also
rejects any product where the FAR 25.106(b)(2) 55% fallback would change the answer, because its
interaction with DFARS 225.502(c) is ambiguous.
