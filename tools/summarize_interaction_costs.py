"""Summarize the diagnostic traces; do not treat ablations as shippable gains."""
import hashlib
import json
from pathlib import Path
from statistics import mean, median

root = Path(__file__).resolve().parents[1]
folder = root / "diagnostics/performance-interaction-costs-20261101"


def Main():
    grouped = {}
    for path in folder.glob("*.json"):
        data = json.loads(path.read_text(encoding = "utf-8"))
        if "mode" in data and data["run"] in range(3):
            grouped.setdefault((data["case"], data["mode"]), []).append(data)
    results = []
    for (case, mode), runs in sorted(grouped.items()):
        assert len(runs) == 3, (case, mode, len(runs))
        samples = [[sample for run in runs for sample in run["samples"][variant]] for variant in range(2)]
        deltas = {key: [b[key] - a[key] for a, b in zip(*samples)] for key in samples[0][0]}
        result = dict(case = case, mode = mode, samplesPerVariant = len(samples[0]),
            medians = [{key: median(sample[key] for sample in rows) for key in rows[0]} for rows in samples],
            means = [{key: mean(sample[key] for sample in rows) for key in rows[0]} for rows in samples],
            pairedMedianDeltaMs = {key: median(values) for key, values in deltas.items()},
            pairedMeanDeltaMs = {key: mean(values) for key, values in deltas.items()},
            perRunPairedMedianDeltaMs = [run["pairedMedianDeltaMs"] for run in sorted(runs, key = lambda row: row["run"])])
        if mode == "normal":
            combined = samples[0] + samples[1]
            result["controlMedians"] = {key: median(row[key] for row in combined) for key in combined[0]}
            firstFrames = [rows[0] for run in runs for rows in run["warmups"]]
            result["firstFrameMedians"] = {key: median(row[key] for row in firstFrames) for key in firstFrames[0]}
            release = [row for run in runs for row in run.get("releaseSamples", [])]
            if release:
                result["releaseMedians"] = {key: median(row[key] for row in release) for key in release[0]}
        results.append(result)
    phases = {}
    accounting = {}
    for path in folder.glob("*-phases-2.json"):
        data = json.loads(path.read_text(encoding = "utf-8"))
        names = set().union(*(row["phases"] for row in data["samples"]))
        phases[data["case"]] = {name: dict(zip(("inclusiveMs", "exclusiveOfInstrumentedChildrenMs", "calls"),
            [median(row["phases"].get(name, [0, 0, 0])[index] for row in data["samples"]) for index in range(3)])) for name in sorted(names)}
        accounting[data["case"]] = median(sum(values[0] for name, values in row["phases"].items()
            if name.endswith(":GeometryCacheCost")) for row in data["samples"])
    assert len(phases) == 10
    scaled = {}
    for case in ("pan", "pan-fractional", "zoom-near"):
        runs = [json.loads((folder / f"{case}-normal-{run}.json").read_text(encoding = "utf-8")) for run in (125, 126)]
        assert all(run["devicePixelRatio"] == 1.25 for run in runs)
        rows = [row for run in runs for samples in run["samples"] for row in samples]
        scaled[case] = {key: median(row[key] for row in rows) for key in rows[0]}
    transitions = {}
    for case in ("pan", "pan-fractional", "pan-wide"):
        runs = [json.loads((folder / f"{case}-transitions-{run}.json").read_text(encoding = "utf-8")) for run in range(3)]
        transitions[case] = {}
        for index, name in enumerate(("start", "release")):
            rows = [run["transitions"][index] for run in runs]
            names = set().union(*(row["phases"] for row in rows))
            transitions[case][name] = dict(medians = {key: median(row[key] for row in rows)
                for key in ("updateMs", "eventMs", "grabMs", "totalMs")},
                inclusivePhaseMedians = {key: median(row["phases"].get(key, [0, 0, 0])[0] for row in rows) for key in names})
    result = dict(methodology = [
        "Original flat.plan, saved settings, 1500x900 logical viewport, Qt offscreen, DPR 1 for main matrix.",
        "Three independent processes per case/bypass; independent real MainWindows, alternating frame order and reversed creation order on alternate runs.",
        "Two warmups and 15 timed frames per window: 45 matched pairs per bypass, 90 normal samples per control case.",
        "Drag: wall 256 vertex 1, wall 1 vertex 0, and wall 256 isolated. Cursor path (25+3*frame,17+frame) relative to drag start.",
        "Zoom-out/in: 17 consecutive wheel ticks from saved camera. Deep: eight outward ticks before the same outward trace. Near: alternating inward/outward ticks.",
        "Pan: actual middle-button press/move/release handlers; (8,5) device pixels per frame. Fractional: (8.25,5.25). Wide: eight outward ticks before panning.",
        "Input handler, processEvents, one synchronous grab. Exactly one paint per measured step asserted. These are work times, not display latency or maximum delivered FPS.",
        "Cyclic automatic GC disabled equally; application timers and explicit collections remain active. First warmup follows project load without an idle pre-render, so it is NOT an ordinary warm pan-start latency.",
        "Warm pan transitions: three separate processes per case, render idle scene twice first, press/paint, 17 pan moves, release/paint; phase wrappers enabled. These probes are separate from uninstrumented steady timings.",
        "125% scaling controls: two independent paired processes per case, 60 normal frames in total, same pixel-aligned/fractional DEVICE movements. A spot check, not a full scaling matrix.",
        "Normal pairs assert model/camera equality every frame and exact final pixels, also exact pan-release pixels. Bypasses preserve camera; model equality asserted except no-snap/frozen-rooms.",
        "Phase timing uses wrappers including separate collision workspaces; phase 2 is current instrumentation. Inclusive times nest and must not be added. Exclusive times exclude only instrumented children.",
        "cProfile runs separately on frame 17 without phase wrappers. Its overhead is not a predicted saving.",
        "no-snap returns the unsnapped point and clears guides; geometry and later paint differ. frozen-rooms skips Check, including background revision changes; shared geometry can be computed elsewhere.",
        "no-qt-draw suppresses Python-dispatched painter draw/fill/stroke calls but keeps text preparation and native SVG rendering. no-artwork suppresses FurnishingSvgRenderer.render, including its preparation and native drawing.",
        "no-edit-cache forces the existing full-scene path; it removes both snapshot overhead and pixel reuse. No ablation is a behavior-preserving optimization; effects overlap and cannot be added.",
        "All bypasses are temporary in-memory patches restored by ExitStack. No production code changes, no help modifications, no Git commands."
    ], results = results, phaseMedians = phases, combinedCacheAccountingMedianMs = accounting,
        scale125ControlMedians = scaled, warmPanTransitions = transitions)
    (folder / "summary.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
    before = json.loads((folder / "source-before.json").read_text(encoding = "utf-8"))
    changed = [name for name, expected in before.items() if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected]
    assert not changed, changed
    verification = dict(productionAndProtectedFilesChecked = len(before), changed = changed,
        normalControlCases = sum(row["mode"] == "normal" for row in results),
        pairedTrials = sum(len(runs) for runs in grouped.values()),
        additionalScale125ControlTrials = 6, warmPanTransitionTrials = 9,
        diagnosticSourceSha256 = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), root / "tools/diagnose_interaction_costs.py")})
    (folder / "verification.json").write_text(json.dumps(verification, indent = 2), encoding = "utf-8")
    for row in results:
        if row["mode"] == "normal":
            print(row["case"], {key: round(value, 2) for key, value in row["controlMedians"].items()})
        else:
            print(row["case"], row["mode"], "paired median/mean delta", round(row["pairedMedianDeltaMs"]["totalMs"], 2), round(row["pairedMeanDeltaMs"]["totalMs"], 2))


if __name__ == "__main__":
    Main()
