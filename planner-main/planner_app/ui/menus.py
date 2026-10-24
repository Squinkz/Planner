"""Shared themed menu rows for header and furnishing context actions."""

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.graphics.theme import HeaderIcon
from .context_submenu import ContextSubmenuController


def AddMenuButton(menu, text, shortcutText = "", iconName = None):
    action = QtWidgets.QWidgetAction(menu)
    button = QtWidgets.QPushButton()
    button.setObjectName("headerMenuItem")
    button.setAccessibleName(text)
    button.setFlat(True)
    button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    button.setMinimumWidth(300)
    row = QtWidgets.QHBoxLayout(button)
    row.setContentsMargins(12, 0, 14, 0)
    row.setSpacing(14)
    iconLabel = QtWidgets.QLabel()
    iconLabel.setObjectName("menuIconLabel")
    iconLabel.setFixedSize(18, 18)
    icon = iconName if isinstance(iconName, QtGui.QIcon) else HeaderIcon(iconName or text)
    iconLabel.setPixmap(icon.pixmap(18, 18))
    textLabel = QtWidgets.QLabel(text)
    textLabel.setObjectName("menuTextLabel")
    textLabel.ensurePolished()
    textLabel.setMinimumWidth(max(126, textLabel.sizeHint().width()))
    shortcutLabel = QtWidgets.QLabel(shortcutText)
    shortcutLabel.setObjectName("menuShortcutLabel")
    shortcutLabel.setMinimumWidth(96 if shortcutText else 0)
    shortcutLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    for label in (iconLabel, textLabel, shortcutLabel):
        label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    row.addWidget(iconLabel)
    row.addWidget(textLabel)
    row.addStretch(1)
    row.addWidget(shortcutLabel)
    button.setMinimumWidth(max(300, row.minimumSize().width() + 4))
    button.iconLabel = iconLabel
    button.shortcutLabel = shortcutLabel
    button.clicked.connect(menu.hide)
    action.setDefaultWidget(button)
    menu.addAction(action)
    return button


def AddSubmenuButton(owner, menu, iconName, text, populateCallback):
    action = QtWidgets.QWidgetAction(menu)
    button = QtWidgets.QPushButton()
    button.setObjectName("headerMenuItem")
    button.setAccessibleName(text)
    button.setCheckable(True)
    button.setFlat(True)
    button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    button.setMinimumWidth(250)
    row = QtWidgets.QHBoxLayout(button)
    row.setContentsMargins(12, 0, 14, 0)
    row.setSpacing(14)

    icon = iconName if isinstance(iconName, QtGui.QIcon) else HeaderIcon(iconName) if iconName else QtGui.QIcon()
    iconLabel = QtWidgets.QLabel()
    iconLabel.setObjectName("menuIconLabel")
    iconLabel.setFixedSize(18, 18)
    if not icon.isNull():
        iconLabel.setPixmap(icon.pixmap(18, 18))
    iconLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    textLabel = QtWidgets.QLabel(text)
    textLabel.setObjectName("menuTextLabel")
    textLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    arrowLabel = QtWidgets.QLabel(">")
    arrowLabel.setObjectName("menuShortcutLabel")
    arrowLabel.setMinimumWidth(24)
    arrowLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    arrowLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    row.addWidget(iconLabel, 0)
    row.addWidget(textLabel, 0)
    row.addStretch(1)
    row.addWidget(arrowLabel, 0)

    controller = ContextSubmenuController(owner, menu, button, populateCallback)
    button._submenuController = controller
    action.setDefaultWidget(button)
    menu.addAction(action)
    return button

