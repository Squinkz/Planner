import os, sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, 'planner-main')
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, SilledWindow, Window, DrawOpeningSymbol
from theme import BuildStyle
app = QtWidgets.QApplication([])
app.setStyleSheet(BuildStyle())
main = MainWindow()
main.show()
app.processEvents()
v = main.viewport
v.unitsMode = 'Adaptive Metric'  # Sill-depth edits below use centimeters.
wall = Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0))
v.walls = [wall]
w = v.PlaceWindow(v.WorldToViewport(QtCore.QPointF()), openingType = SilledWindow)
assert isinstance(w, SilledWindow)
assert w.sillDepth == 40 and main.propertyFields['sillDepth'].value() == 4
main.EditProperty('sillDepth', 8)
assert w.sillDepth == 80
v.Undo()
assert w.sillDepth == 40
v.Redo()
assert w.sillDepth == 80
assert v.CloneOpening(w, wall).sillDepth == 80
assert v.InactiveOpening(QtCore.QPointF(), SilledWindow, w).sillDepth == 80
assert main.selectionLabel.text().startswith('Silled Window')
assert main.doorProperties.isVisible()
assert main.doorProperties.layout().labelForField(main.doorFields['swing']).text() == 'Facing'
assert main.doorFields['swing'].isVisible() and not main.doorFields['hinge'].isVisible()
main.EditDoorProperty('swing')
assert w.swingsOutwards
v.Undo()
assert not w.swingsOutwards
v.Redo()
assert w.swingsOutwards
assert v.CloneOpening(w, wall).swingsOutwards
assert v.InactiveOpening(QtCore.QPointF(), SilledWindow, w).swingsOutwards
v.OrientDoor(w, v.WorldToViewport(QtCore.QPointF(0, 500)))
assert w.swingsOutwards
v.OrientDoor(w, v.WorldToViewport(QtCore.QPointF(0, -500)))
assert not w.swingsOutwards
small = Wall(QtCore.QPointF(5000, 0), QtCore.QPointF(5500, 0))
v.walls.append(small)
preview = v.FindWindowPlacement(v.WorldToViewport(QtCore.QPointF(5250, 0)), 1200, openingType = SilledWindow)
assert isinstance(preview, SilledWindow) and abs(preview.length - 500) < .01
main.silledWindowButton.icon().pixmap(40, 40).save('screenshots/silled-window-icon.png')
v.SetSelection([(w, None)])
v.ResetView()
app.processEvents()
v.grab().save('screenshots/silled-window-preview.png')
main.close()
print('PASS: placement, shrink to fit, facing panel, flip undo/redo, cloning and Ctrl orientation')
