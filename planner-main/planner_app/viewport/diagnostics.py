"""Opt-in, bounded CPU/event-loop diagnostics; no native presentation claims."""
from collections import Counter, deque
from functools import wraps
import gc
import json
from pathlib import Path
import platform
from threading import RLock, get_ident
from time import perf_counter
import weakref
from PySide6 import QtCore


def MeasurePaint(function):
    @wraps(function)
    def Measured(self, *args, **kwargs):
        diagnostics = getattr(self, "renderDiagnostics", None)
        if diagnostics is None or not diagnostics.enabled:
            return function(self, *args, **kwargs)
        started = perf_counter()
        try:
            return function(self, *args, **kwargs)
        finally:
            diagnostics.RecordPaint(started, perf_counter())
    return Measured


def MeasureRecoveryWrite(function):
    """Time worker serialization/I/O without calling Qt from the recovery thread."""
    @wraps(function)
    def Measured(self, *args, diagnostics = None, jobId = None, **kwargs):
        if diagnostics is None or not diagnostics.enabled:
            return function(self, *args, **kwargs)
        started = perf_counter()
        diagnostics.RecordRecovery("started", jobId)
        outcome = "exception"
        try:
            error = function(self, *args, **kwargs)
            outcome = "failed" if error is not None else "saved"
            return error
        finally:
            diagnostics.RecordRecovery("finished", jobId, durationMs = (perf_counter() - started) * 1000,
                                       outcome = outcome)
    return Measured


def MeasureRecoveryCheckpoint(function):
    @wraps(function)
    def Measured(self, *args, **kwargs):
        diagnostics = getattr(self.viewport, "renderDiagnostics", None)
        if diagnostics is None or not diagnostics.enabled:
            return function(self, *args, **kwargs)
        started = perf_counter()
        try:
            return function(self, *args, **kwargs)
        finally:
            diagnostics.RecordPhase("recovery-checkpoint", started)
    return Measured


class RenderDiagnostics(QtCore.QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.enabled = False
        self.events = deque(maxlen = 2048)
        self.paints = deque(maxlen = 2048)
        self.inputs = deque(maxlen = 2048)
        self.loopDelays = deque(maxlen = 2048)
        self.cacheCounts = Counter()
        self.inputAt = None
        self.oldestInputAt = None
        self.inputSequence = 0
        self.paintedInputSequence = 0
        self.inputClockOffset = None
        self.lastInputTimestamp = None
        self.lastPaintAt = None
        self.lastTickAt = None
        self.eventLock = RLock()
        self.guiThreadId = get_ident()
        self.environment = {"python": platform.python_version(), "qt": QtCore.qVersion(),
                            "platform": platform.platform(), "clock": "perf_counter", "guiThreadId": self.guiThreadId}
        self.recoveryJobId = 0
        self.gcStarted = {}
        reference = weakref.ref(self)

        def GcCallback(phase, info):
            diagnostics = reference()
            if diagnostics is None or not diagnostics.enabled:
                return
            threadId = get_ident()
            generation = info["generation"]
            key = (threadId, generation)
            with diagnostics.eventLock:
                if phase == "start":
                    diagnostics.gcStarted[key] = perf_counter()
                else:
                    started = diagnostics.gcStarted.pop(key, None)
                    if started is not None:
                        diagnostics.RecordEvent({"kind": "gc", "at": started,
                                                 "durationMs": (perf_counter() - started) * 1000,
                                                 "generation": generation, "collected": info["collected"],
                                                 "uncollectable": info["uncollectable"], "threadId": threadId,
                                                 "onGuiThread": threadId == diagnostics.guiThreadId})
        self.gcCallback = GcCallback
        # A weak callback cannot retain the viewport. Remove it even when Qt destroys
        # the parent without an explicit Stop call.
        def RemoveGcCallback():
            if GcCallback in gc.callbacks:
                gc.callbacks.remove(GcCallback)
        self.destroyed.connect(RemoveGcCallback)
        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.Tick)

    def Start(self):
        self.enabled = True
        self.inputAt = self.oldestInputAt = None
        self.paintedInputSequence = self.inputSequence
        self.inputClockOffset = self.lastInputTimestamp = None
        if self.gcCallback not in gc.callbacks:
            gc.callbacks.append(self.gcCallback)
        self.lastTickAt = perf_counter()
        self.timer.start()

    def Stop(self):
        self.enabled = False
        if self.gcCallback in gc.callbacks:
            gc.callbacks.remove(self.gcCallback)
        with self.eventLock:
            self.gcStarted.clear()
        self.timer.stop()
        self.inputAt = None
        self.oldestInputAt = None

    def RecordInput(self, event):
        now = perf_counter()
        timestamp = event.timestamp()
        queueLag = None
        if timestamp:
            offset = now - timestamp / 1000
            if self.lastInputTimestamp is not None and timestamp < self.lastInputTimestamp:
                self.inputClockOffset = None
            self.inputClockOffset = offset if self.inputClockOffset is None else min(self.inputClockOffset, offset)
            self.lastInputTimestamp = timestamp
            queueLag = max(0.0, (offset - self.inputClockOffset) * 1000)
        self.inputAt = now
        if self.oldestInputAt is None:
            self.oldestInputAt = now
        self.inputSequence += 1
        viewport = self.parent()
        sample = {"at": now, "sequence": self.inputSequence, "timestampMs": timestamp,
                  "relativeQueueLagMs": queueLag, "type": event.type().name, "panning": viewport.isPanning,
                  "spontaneous": event.spontaneous()}
        if hasattr(event, "position"):
            position = event.position()
            sample["position"] = [position.x(), position.y()]
        self.inputs.append(sample)

    def Tick(self):
        now = perf_counter()
        delay = max(0.0, (now - self.lastTickAt) * 1000 - self.timer.interval())
        self.lastTickAt = now
        self.loopDelays.append(delay)
        if delay > 16.7:
            self.RecordEvent({"kind": "eventLoopDelay", "at": now, "durationMs": delay})

    def RecordPaint(self, started, finished):
        sample = {"at": started, "durationMs": (finished - started) * 1000,
                  "intervalMs": (started - self.lastPaintAt) * 1000 if self.lastPaintAt is not None else None,
                  "inputAgeMs": (started - self.inputAt) * 1000 if self.inputAt is not None else None,
                  "oldestInputAgeMs": (started - self.oldestInputAt) * 1000 if self.oldestInputAt is not None else None,
                  "inputSequence": self.inputSequence, "inputsSincePaint": self.inputSequence - self.paintedInputSequence,
                  "panning": self.parent().isPanning,
                  "panOffset": [self.parent().panOffset.x(), self.parent().panOffset.y()]}
        self.paints.append(sample)
        self.lastPaintAt = started
        self.inputAt = None
        self.oldestInputAt = None
        self.paintedInputSequence = self.inputSequence
        if sample["durationMs"] > 16.7:
            self.RecordEvent({"kind": "slowPaint", **sample})

    def RecordCache(self, cache, result, reason):
        self.cacheCounts[(cache, result, reason)] += 1
        if result != "hit":
            self.RecordEvent({"kind": "cache", "at": perf_counter(), "cache": cache,
                              "result": result, "reason": reason})

    def RecordPhase(self, name, started):
        self.RecordEvent({"kind": "phase", "at": started, "name": name,
                          "durationMs": (perf_counter() - started) * 1000})

    def RecordEvent(self, event):
        with self.eventLock:
            self.events.append(event)

    def BeginRecovery(self, wait):
        self.recoveryJobId += 1
        self.RecordRecovery("submitted", self.recoveryJobId, synchronous = wait)
        return self.recoveryJobId

    def RecordRecovery(self, stage, jobId, **details):
        if self.enabled:
            threadId = get_ident()
            self.RecordEvent({"kind": "recovery", "at": perf_counter(), "stage": stage, "jobId": jobId,
                              "threadId": threadId, "onGuiThread": threadId == self.guiThreadId, **details})

    def Report(self):
        with self.eventLock:
            events = list(self.events)
        summary = {}
        measurements = {
            "paintCpuMs": [sample["durationMs"] for sample in self.paints],
            "paintIntervalMs": [sample["intervalMs"] for sample in self.paints if sample["intervalMs"] is not None],
            "inputToPaintMs": [sample["inputAgeMs"] for sample in self.paints if sample["inputAgeMs"] is not None],
            "oldestInputToPaintMs": [sample["oldestInputAgeMs"] for sample in self.paints if sample["oldestInputAgeMs"] is not None],
            "relativeInputQueueLagMs": [sample["relativeQueueLagMs"] for sample in self.inputs if sample["relativeQueueLagMs"] is not None],
            "panPaintIntervalMs": [sample["intervalMs"] for sample in self.paints if sample["panning"] and sample["intervalMs"] is not None],
            "eventLoopDelayMs": list(self.loopDelays),
        }
        for name, samples in measurements.items():
            ordered = sorted(samples)
            summary[name] = {"count": len(ordered),
                             **{f"p{percentile}": ordered[round((len(ordered) - 1) * percentile / 100)] if ordered else None
                                for percentile in (50, 95, 99)},
                             "max": ordered[-1] if ordered else None,
                             **{f"over{threshold}Ms": sum(value > threshold for value in ordered)
                                for threshold in (16.7, 33, 50)}}
        viewport = self.parent()
        rasterBudget = getattr(viewport, "rasterCacheBudget", None)
        rasterReport = ({"limitBytes": viewport.viewportRasterByteLimit, "retainedBytes": rasterBudget.RetainedBytes(),
                         "peakAdmittedBytes": rasterBudget.peakBytes, "evictions": rasterBudget.evictions}
                        if rasterBudget is not None else None)
        return {"version": 1, "environment": self.environment, "summary": summary, "rasterCache": rasterReport,
                "framePacing": {"screenRefreshRateHz": viewport.screen().refreshRate(),
                                "panFrameIntervalMs": viewport.panFrameInterval * 1000},
                "cacheCounts": [{"cache": cache, "result": result, "reason": reason, "count": count}
                                for (cache, result, reason), count in sorted(self.cacheCounts.items())],
                "paints": list(self.paints), "inputs": list(self.inputs), "events": events}

    def Write(self, path):
        Path(path).write_text(json.dumps(self.Report(), indent = 2) + "\n", encoding = "utf-8")
