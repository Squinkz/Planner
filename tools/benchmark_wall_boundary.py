"""Isolated frozen/current wall-boundary trials using the existing drag harness."""
import argparse
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "checks"), str(root / "tools")]
import benchmark_local_paint
from check_wall_boundary import Baseline


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--case", choices = ("drag", "zoom-out"), default = "drag")
    parser.add_argument("--wall-id", dest = "wallId", type = int, default = 256)
    parser.add_argument("--vertex", type = int, default = 1)
    parser.add_argument("--single-wall", dest = "singleWall", action = "store_true")
    parser.add_argument("--run-index", dest = "runIndex", type = int)
    args = parser.parse_args()
    folder = root / "diagnostics/performance-wall-boundary-20261101"
    folder.mkdir(exist_ok = True)
    stem = f"benchmark-{args.case}-{args.wallId}-{args.vertex}" + ("-single" if args.singleWall else "")
    if args.runIndex is not None:
        with patch.object(benchmark_local_paint, "Baseline", Baseline):
            result = benchmark_local_paint.RunTrial(args, args.runIndex)
        (folder / f"{stem}-run{args.runIndex}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
        return
    runs = []
    for run in range(4):
        arguments = [sys.executable, str(Path(__file__).resolve()), "--case", args.case,
                     "--wall-id", str(args.wallId), "--vertex", str(args.vertex), "--run-index", str(run)]
        if args.singleWall:
            arguments.append("--single-wall")
        subprocess.run(arguments, cwd = root, check = True)
        runs.append(json.loads((folder / f"{stem}-run{run}.json").read_text()))
    samples = [[row for run in runs for row in run["samples"][variant]] for variant in range(2)]
    result = dict(case = args.case, wallId = args.wallId, vertex = args.vertex, singleWall = args.singleWall,
                  medians = [{key: median(row[key] for row in rows) for key in rows[0]} for rows in samples], runs = runs,
                  methodology = "Frozen start-of-pass ConnectedWallPath versus current; all other code shared. "
                  "Four fresh processes with two hidden MainWindows each; alternating creation and input order. "
                  "Two warmups and 15 unprofiled frames per variant per run, 60 samples total; 1500x900, GC disabled equally. "
                  "Input, events and one synchronous grab; exactly one paint per frame. Model/gesture state compared "
                  "every frame and final pixels every trial. Not display latency or isolated cold-start measurements.")
    (folder / f"{stem}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
    print(json.dumps(result["medians"], indent = 2))


if __name__ == "__main__":
    Main()
