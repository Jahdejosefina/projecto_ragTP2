"""
Runs the stage `.py` files in order, as plain scripts, and stops at the first failure.

    python tools/run_stages.py                  # every stage that exists
    python tools/run_stages.py --from 03 --to 05

For local SMOKE_TEST validation: each stage runs in its own process from the repo root,
its output is shown and also saved to `artifacts/logs/NN_stem.log`, and a table of wall
times is printed at the end. A stage that doesn't exist yet is skipped.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from py_to_notebook import STAGE_STEMS  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # a piped Windows console is cp1252: Spanish would crash it
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="00")
    ap.add_argument("--to", dest="end", default="99")
    args = ap.parse_args()

    stems = [s for s in STAGE_STEMS if args.start <= s[:2] <= args.end and (ROOT / f"{s}.py").is_file()]
    if not stems:
        print("no stages to run")
        return 1
    logs = ROOT / "artifacts" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"}
    timings = []
    for stem in stems:
        print(f"\n{'=' * 78}\n>>> {stem}\n{'=' * 78}", flush=True)
        t0 = time.time()
        with open(logs / f"{stem}.log", "w", encoding="utf-8", newline="\n") as log:
            proc = subprocess.Popen([sys.executable, f"{stem}.py"], cwd=ROOT, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                sys.stdout.write(line)
                log.write(line)
            code = proc.wait()
        timings.append((stem, time.time() - t0, code))
        if code != 0:
            print(f"\n{stem} FAILED (exit {code}); log: {logs / (stem + '.log')}")
            break
    print(f"\n{'stage':<24} {'seconds':>8}  result")
    for stem, secs, code in timings:
        print(f"{stem:<24} {secs:8.1f}  {'ok' if code == 0 else f'FAILED ({code})'}")
    return 0 if all(c == 0 for _, _, c in timings) and len(timings) == len(stems) else 1


if __name__ == "__main__":
    sys.exit(main())
