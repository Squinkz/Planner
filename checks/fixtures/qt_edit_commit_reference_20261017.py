"""Unchanged desktop commit coordinator bound to the frozen edit engine."""
import time
from planner_app.models import Stair
from .qt_edit_transactions_reference_20261017 import SceneEdit

class ReferenceCommit:
    def RecordEdit(self, before, coalesceKey = None):
        self.EnsureObjectIds(before)
        self.PruneObjectGroups()
        for stair in self.walls:
            if isinstance(stair, Stair) and not stair.autosize:
                stair.manualStepCount = stair.stepCount
        sceneIds = {id(obj) for obj in self.walls + self.windows + self.furnishings + self.labels}
        if before is not None:
            for entry in before[0]:
                if isinstance(entry[0], Stair) and id(entry[0]) not in sceneIds:
                    # Detached stairs must not retain the rest of their old scene.
                    # Restoring them rebuilds these layout links in EnsureObjectIds.
                    entry[0].sceneStairs = []
        self.hiddenObjects = [obj for obj in self.hiddenObjects if id(obj) in sceneIds]
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        after = self.CaptureState()
        edit = SceneEdit.Between(before, after) if before is not None else None
        if edit is not None:
            now = time.monotonic()
            if (coalesceKey is not None and coalesceKey == getattr(self, "historyCoalesceKey", None)
                    and now - getattr(self, "historyCoalesceTime", 0) <= 1.0 and self.undoHistory
                    and getattr(self, "historyCoalesceRevision", None) == self.sceneRevision):
                original = self.undoHistory[-1].Apply(before, False, validate = True)
                self.undoHistory.pop()
                edit = SceneEdit.Between(original, after)
            if edit is not None:
                self.undoHistory.append(edit)
            self.historyCoalesceKey, self.historyCoalesceTime = coalesceKey, now
            self.redoHistory.clear()
            # Strict count and retained-payload bounds. An oversized single edit
            # cannot retain an unbounded scene through deleted model references.
            totalBytes = sum(item.byteSize for item in self.undoHistory)
            while self.undoHistory and (len(self.undoHistory) > self.historyLimit or totalBytes > self.historyByteBudget):
                totalBytes -= self.undoHistory.pop(0).byteSize
            self.sceneRevision += 1
            self.historyCoalesceRevision = self.sceneRevision
            self.sceneChanged.emit()
