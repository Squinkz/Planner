"""Dropdown models remain correctly typed when deleted item addresses are reused."""
import gc
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.ui.widgets import DownwardComboBox


def Main():
    app = QtWidgets.QApplication([])
    retainedItems = []
    # Export sections retain QStandardItem wrappers on their panel. The panel's
    # Python wrapper can outlive its deleted native widgets during replacement.
    for index in range(2000):
        combo = DownwardComboBox()
        combo.addItems(("Section", "Choice"))
        model = combo.model()
        assert isinstance(model, QtGui.QStandardItemModel), type(model)
        item = model.item(0)
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        retainedItems.append(item)
        del model, item
        combo.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        if index % 100 == 0:
            gc.collect()
    retainedItems.clear()
    gc.collect()
    combo = DownwardComboBox()
    combo.addItem("Short")
    combo.show()
    app.processEvents()
    width = combo.minimumWidth()
    combo.addItem("A substantially longer dropdown choice")
    assert combo.minimumWidth() > width
    combo.model().setData(combo.model().index(1, 0), "Tiny")
    assert combo.minimumWidth() == width
    combo.model().clear()
    assert combo.count() == 0
    combo.close()
    combo.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    print("2000 dropdown teardown/recreation cycles and model-driven width updates passed")


if __name__ == "__main__":
    Main()
