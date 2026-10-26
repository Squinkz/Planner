"""Theme-driven widget styles, material patterns and header icons."""

import re
from PySide6 import QtCore, QtGui
from .icons import UiIcon, UiIconPath, ThemeIcon, themeIconCache, PruneArtworkCaches, artworkCacheLimit
from .palette import themeColors
from planner_app.preferences import wallPresetWidths
from .fonts import fontFamily, LoadApplicationFonts


wallMaterials = ("Generic", "Brick", "Concrete Block", "Ceramic", "Concrete", "Lumber", "Metal", "Plywood", "Steel", "Wood")
materialPatternSpacings = {"Brick": 10, "Concrete Block": 10, "Ceramic": 22, "Concrete": 32,
                          "Lumber": 10, "Metal": 24, "Plywood": 32, "Steel": 14, "Wood": 48}
# Match the former grid's perceived brightness over the dark canvas.
gridIntensityDefaults = {"overall": 1.0, "major": .169, "minor": .083, "origin": .305}


def ApplyApplicationTheme(app):
    LoadApplicationFonts(app)
    app.setStyleSheet(BuildStyle())
    applicationPalette = app.palette()
    for role, color in (("Window", "windowBackground"), ("WindowText", "text"),
                        ("Base", "fieldBackground"), ("AlternateBase", "controlBackground"),
                        ("Text", "text"), ("Button", "controlBackground"), ("ButtonText", "text"),
                        ("Highlight", "activeBackground"), ("HighlightedText", "activeText"),
                        ("ToolTipBase", "controlBackground"), ("ToolTipText", "text"),
                        ("PlaceholderText", "mutedText")):
        applicationPalette.setColor(getattr(QtGui.QPalette.ColorRole, role), QtGui.QColor(themeColors[color]))
    for role in (QtGui.QPalette.ColorRole.Text, QtGui.QPalette.ColorRole.ButtonText, QtGui.QPalette.ColorRole.WindowText):
        applicationPalette.setColor(QtGui.QPalette.ColorGroup.Disabled, role, QtGui.QColor(themeColors["disabled"]))
    app.setPalette(applicationPalette)


def WallPresetIcon(index):
    cacheKey = ("wall-preset", index, tuple(themeColors.items()))
    cached = themeIconCache.get(cacheKey)
    if cached is not None:
        return ThemeIcon(cached, cached.factory)
    pixmap = QtGui.QPixmap(24, 28)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    width = 3 + wallPresetWidths[index] / 2
    painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["icon"]), 1))
    painter.setBrush(BuildWallBrush())
    painter.drawRect(QtCore.QRectF(12 - width / 2, 5, width, 18))
    painter.end()
    icon = ThemeIcon(pixmap, lambda: WallPresetIcon(index))
    themeIconCache[cacheKey] = icon
    if len(themeIconCache) > artworkCacheLimit:
        PruneArtworkCaches(force = False)
    return icon


def BuildWallBrush(selected = False, material = "Generic", warning = False, grouped = False):
    selectedBackground = themeColors["groupSelectionFill"] if grouped else themeColors["selectionFill"]
    if material == "Generic":
        return QtGui.QBrush(QtGui.QColor(themeColors["warningFill"] if warning else selectedBackground if selected else themeColors["wallFill"]))
    spacing = materialPatternSpacings[material]
    tile = QtGui.QPixmap(spacing, spacing)
    tile.fill(QtGui.QColor(themeColors["warningFill"] if warning else selectedBackground if selected else themeColors["wallFill"]))
    painter = QtGui.QPainter(tile)
    painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["warningOutline"] if warning else (themeColors["groupSelectionOutline"] if grouped else themeColors["selectionOutline"]) if selected else themeColors["materialPattern"]), 1))
    DrawMaterialPattern(painter, material, spacing)
    painter.end()
    return QtGui.QBrush(tile)


def DrawMaterialPattern(painter, material, spacing):
    """Draw a material tile with shared commands for bitmap and vector exports."""
    if material == "Concrete":
        for x, y in ((3, 5), (14, 2), (27, 9), (8, 18), (22, 23), (3, 29), (17, 13), (30, 30)):
            painter.drawPoint(x, y)
    elif material == "Wood":
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for x in range(-12, spacing + 13, 12):
            grain = QtGui.QPainterPath(QtCore.QPointF(x, 0))
            grain.cubicTo(x + 12, 16, x - 12, 32, x, 48)
            painter.drawPath(grain)
    elif material != "Lumber":
        for offset in range(-spacing, spacing * 3, spacing):
            painter.drawLine(offset - spacing, spacing, offset + spacing, -spacing)
            if material in ("Metal", "Plywood", "Steel"):
                painter.drawLine(offset - spacing + 3, spacing, offset + spacing + 3, -spacing)
            if material in ("Concrete Block", "Ceramic"):
                painter.drawLine(offset - spacing, -spacing, offset + spacing, spacing)
        if material == "Plywood":
            for y in range(0, spacing, 8):
                painter.drawLine(0, y, spacing, y)


def MaterialIcon(material):
    cacheKey = ("material", material, tuple(themeColors.items()))
    cached = themeIconCache.get(cacheKey)
    if cached is not None:
        return ThemeIcon(cached, cached.factory)
    # Reserve eight logical pixels after the square swatch for its text label.
    pixmap = QtGui.QPixmap(64, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    brush = BuildWallBrush(material = material)
    brush.setTransform(QtGui.QTransform().scale(.5, .5))
    bounds = QtCore.QRectF(1, 1, 22, 22)
    painter.fillRect(bounds, brush)
    painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["mutedText"]), 1))
    if material == "Lumber":
        painter.drawLine(bounds.topLeft(), bounds.bottomRight())
        painter.drawLine(bounds.bottomLeft(), bounds.topRight())
    painter.drawRect(bounds)
    painter.end()
    icon = ThemeIcon(pixmap, lambda: MaterialIcon(material))
    themeIconCache[cacheKey] = icon
    if len(themeIconCache) > artworkCacheLimit:
        PruneArtworkCaches(force = False)
    return icon


def BuildCanvasStyle():
    """Canvas-colored controls refresh locally, independently of the UI stylesheet."""
    return (f'QPushButton#openingIconButton[placementActive="true"] {{ background: {themeColors["selectionFill"]}; '
            f'border-color: {themeColors["selectionOutline"]}; }}')


def BuildStyle():
    if QtGui.QGuiApplication.instance() is not None:
        LoadApplicationFonts()
    style = """
QWidget {
    background: __COLOR_windowBackground__;
    color: __COLOR_text__;
    font-family: "__FONT_FAMILY__";
    font-size: 10pt;
}
QPushButton#headerButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0;
}
QPushButton#headerButton:hover { background: __COLOR_hoverBackground__; }
QPushButton#headerButton:pressed { background: __COLOR_pressedBackground__; }
QPushButton#headerButton:checked { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; }
QMenu {
    background: __COLOR_controlBackground__;
    border: 1px solid __COLOR_menuBorder__;
    padding: 4px;
}
QMenu::separator { height: 1px; background: __COLOR_border__; margin: 4px 6px; }
QPushButton#headerMenuItem {
    background: transparent; border: 1px solid transparent; color: __COLOR_text__;
    border-radius: 4px; padding: 7px 0; min-height: 24px; text-align: left;
}
QPushButton#headerMenuItem:hover { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; color: __COLOR_activeText__; }
QPushButton#headerMenuItem QLabel { background: transparent; color: __COLOR_text__; }
QPushButton#headerMenuItem:hover QLabel { color: __COLOR_activeText__; }
QPushButton#headerMenuItem QLabel#menuShortcutLabel { color: __COLOR_mutedText__; font-size: 8pt; }
QPushButton#headerMenuItem:hover QLabel#menuShortcutLabel { color: __COLOR_activeText__; }
QPushButton#headerMenuItem:checked { background: __COLOR_activeBackground__; color: __COLOR_activeText__; }
QPushButton#headerMenuItem:checked QLabel { color: __COLOR_activeText__; }
QPushButton#headerMenuItem[forceIdle="true"] { background: transparent; border-color: transparent; color: __COLOR_text__; }
QPushButton#headerMenuItem[forceIdle="true"] QLabel { color: __COLOR_text__; }
QPushButton#headerMenuItem[forceIdle="true"] QLabel#menuShortcutLabel { color: __COLOR_mutedText__; }
QPushButton#headerMenuItem:disabled { background: transparent; border-color: transparent; color: __COLOR_disabled__; }
QPushButton#headerMenuItem QLabel:disabled { color: __COLOR_disabled__; }
QPushButton#viewportMenuItem {
    background: transparent;
    border: 1px solid transparent;
    color: __COLOR_text__;
    border-radius: 4px;
    padding: 7px 28px 7px 14px;
    min-height: 24px;
    text-align: left;
}
QPushButton#viewportMenuItem:hover,
QPushButton#viewportMenuItem:checked {
    background: __COLOR_activeBackground__;
    border-color: __COLOR_activeBackground__;
    color: __COLOR_activeText__;
}
QPushButton#viewportMenuItem QLabel { background: transparent; color: __COLOR_text__; }
QPushButton#viewportMenuItem:hover QLabel,
QPushButton#viewportMenuItem:checked QLabel { color: __COLOR_activeText__; }
QPushButton#viewportMenuItem QLabel#menuShortcutLabel { color: __COLOR_mutedText__; font-size: 8pt; }
QPushButton#viewportMenuItem:hover QLabel#menuShortcutLabel,
QPushButton#viewportMenuItem:checked QLabel#menuShortcutLabel { color: __COLOR_activeText__; }
QPushButton {
    background: __COLOR_controlBackground__;
    border: 1px solid __COLOR_controlBackground__;
    border-radius: 5px;
    padding: 4px 12px;
    min-height: 22px;
}
QPushButton:hover { background: __COLOR_hoverBackground__; border-color: __COLOR_hoverBackground__; }
QPushButton:pressed { background: __COLOR_pressedBackground__; border-color: __COLOR_pressedBackground__; }
QPushButton:checked { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; color: __COLOR_activeText__; }
QPushButton:checked:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; }
QPushButton:disabled { background: __COLOR_disabledBackground__; border-color: __COLOR_disabledBackground__; color: __COLOR_disabled__; }
QPushButton#propertyIconButton, QPushButton#settingsIconButton { padding: 0; min-height: 30px; }
QMessageBox QPushButton { max-height: 22px; }
QLabel#openingIconCaption { color: __COLOR_mutedText__; font-size: 8pt; }
QLabel#furnishingDimensions { color: __COLOR_mutedText__; font-size: 7pt; font-weight: 400; }
QLabel#furnishingNoResults { color: __COLOR_mutedText__; }
QPushButton#openingIconButton {
    padding: 0;
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
}
QToolButton#viewportToolbarButton { background: __COLOR_controlBackground__; border: 1px solid __COLOR_controlBackground__; border-radius: 5px; padding: 0; }
QToolButton#viewportToolbarButton:hover { background: __COLOR_hoverBackground__; border-color: __COLOR_hoverBackground__; }
QToolButton#viewportToolbarButton:pressed { background: __COLOR_pressedBackground__; border-color: __COLOR_pressedBackground__; }
QToolButton#viewportToolbarButton:checked { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; }
QToolButton#viewportToolbarButton:checked:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; }
QToolButton#viewportToolbarButton[modeSelector="true"] { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; }
QToolButton#viewportToolbarButton[modeSelector="true"]:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; }
QToolButton#viewportToolbarButton[modeSelector="true"]:pressed { background: __COLOR_pressedBackground__; border-color: __COLOR_pressedBackground__; }
QToolButton#exportBrowseButton { background: __COLOR_controlBackground__; border: 1px solid __COLOR_controlBackground__; border-radius: 4px; padding: 0; }
QToolButton#exportBrowseButton:hover { background: __COLOR_hoverBackground__; border-color: __COLOR_hoverBackground__; }
QToolButton#exportBrowseButton:pressed { background: __COLOR_pressedBackground__; border-color: __COLOR_pressedBackground__; }
QCheckBox { spacing: 8px; }
QTreeWidget#visibilityTree { background: __COLOR_windowBackground__; color: __COLOR_text__; border: none; }
QTreeWidget#visibilityTree::item { padding: 8px 4px; }
QTreeWidget#visibilityTree::item:hover { background: __COLOR_controlBackground__; }
QPushButton#fullscreenButton {
    background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 0;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
}
QPushButton#fullscreenButton:hover { background: __COLOR_hoverBackground__; border-color: __COLOR_hoverBackground__; }
QPushButton#fullscreenButton:pressed { background: __COLOR_pressedBackground__; border-color: __COLOR_pressedBackground__; }
QMenu#snapMenu QPushButton#headerMenuItem:checked { background: transparent; border-color: transparent; }
QMenu#snapMenu QPushButton#headerMenuItem:checked:hover { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; }
QCheckBox:disabled { color: __COLOR_disabled__; }
QCheckBox::indicator, QTreeWidget::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked, QTreeWidget::indicator:unchecked { image: url("__ICON_radio_button_unchecked__"); }
QCheckBox::indicator:checked, QTreeWidget::indicator:checked { image: url("__ICON_radio_button_checked__"); }
QCheckBox::indicator:indeterminate, QTreeWidget::indicator:indeterminate { image: url("__ICON_radio_button_halfchecked__"); }
QCheckBox::indicator:unchecked:disabled, QTreeWidget::indicator:unchecked:disabled { image: url("__ICON_radio_button_unchecked_disabled__"); }
QCheckBox::indicator:checked:disabled, QTreeWidget::indicator:checked:disabled { image: url("__ICON_radio_button_checked_disabled__"); }
QCheckBox::indicator:indeterminate:disabled, QTreeWidget::indicator:indeterminate:disabled { image: url("__ICON_radio_button_halfchecked_disabled__"); }
QGroupBox {
    border: 1px solid __COLOR_border__;
    border-radius: 6px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QFrame#propertiesDivider { background: __COLOR_border__; border: none; }
QFrame#sectionHeadingLine { color: __COLOR_border__; background: __COLOR_border__; max-height: 1px; }
QFrame#wallToolDivider { color: __COLOR_border__; background: __COLOR_border__; max-width: 1px; }
QLabel#selectionHeading { font-size: 14pt; font-weight: 600; }
QLabel#objectSubheading { font-weight: 700; }
QLabel#exportResolution { color: __COLOR_mutedText__; font-style: italic; }
QPushButton#exportActionButton {
    background: __COLOR_activeBackground__; border: 1px solid __COLOR_activeBackground__;
    color: __COLOR_activeText__; border-radius: 5px; font-weight: 700;
    padding: 4px 12px; min-height: 38px; max-height: 38px;
}
QPushButton#exportActionButton:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; }
QPushButton#exportActionButton:pressed { background: __COLOR_pressedBackground__; border-color: __COLOR_pressedBackground__; }
QPushButton#exportSectionHeading {
    background: __COLOR_controlBackground__; border: 1px solid __COLOR_controlBackground__;
    border-top-left-radius: 5px; border-top-right-radius: 5px;
    color: __COLOR_mutedText__; font-size: 14px; font-weight: 600;
    padding: 2px 14px; min-height: 34px; max-height: 34px;
}
QPushButton#exportSectionHeading:checked {
    background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; color: __COLOR_activeText__;
}
QPushButton#exportSectionHeading:hover { background: __COLOR_hoverBackground__; color: __COLOR_text__; }
QPushButton#exportSectionHeading:checked:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; color: __COLOR_activeText__; }
QPushButton#exportSectionHeading:pressed { background: __COLOR_pressedBackground__; }
QPushButton#exportSectionHeading:focus { border: 1px solid __COLOR_border__; }
QGroupBox#vertexProperties { font-size: 12pt; font-weight: 600; }
QLineEdit, QTextEdit, QPlainTextEdit {
    background: __COLOR_fieldBackground__;
    color: __COLOR_text__;
    border: 1px solid __COLOR_fieldBackground__;
    border-radius: 4px;
    padding: 4px;
    selection-background-color: __COLOR_activeBackground__;
}
QAbstractSpinBox QLineEdit, QComboBox QLineEdit {
    border: none; padding: 0;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    background: __COLOR_disabledBackground__; border-color: __COLOR_disabledBackground__; color: __COLOR_disabled__;
}
QDoubleSpinBox, QSpinBox {
    background: __COLOR_fieldBackground__;
    border: 1px solid __COLOR_fieldBackground__;
    border-radius: 4px;
    padding: 4px;
    min-width: 60px;
    min-height: 22px;
    selection-background-color: __COLOR_activeBackground__;
}
QDoubleSpinBox:disabled, QSpinBox:disabled { background: __COLOR_disabledBackground__; border-color: __COLOR_disabledBackground__; color: __COLOR_disabled__; }
QComboBox {
    background: __COLOR_fieldBackground__;
    border: 1px solid __COLOR_fieldBackground__;
    border-radius: 5px;
    padding: 4px 6px 4px 10px;
    min-height: 22px;
}
QComboBox:hover { border-color: __COLOR_hoverBackground__; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid __COLOR_controlBackground__;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    background: __COLOR_controlBackground__;
}
QComboBox::drop-down:hover { background: __COLOR_hoverBackground__; }
QComboBox::down-arrow {
    image: url("__ICON_arrow_drop_down__"); width: 16px; height: 16px;
}
QComboBox QAbstractItemView {
    background: __COLOR_controlBackground__; border: 1px solid __COLOR_menuBorder__; padding: 4px;
    selection-background-color: __COLOR_activeBackground__;
    selection-color: __COLOR_activeText__;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 5px 14px;
    border-radius: 4px;
}
QComboBox QAbstractItemView::item:selected {
    background: __COLOR_activeBackground__;
    color: __COLOR_activeText__;
}
QComboBox:disabled { color: __COLOR_disabled__; background: __COLOR_disabledBackground__; border-color: __COLOR_disabledBackground__; }
QComboBox::drop-down:disabled { background: __COLOR_disabledBackground__; border-color: __COLOR_disabledBackground__; }
QLineEdit#furnishingSearch {
    border-radius: 4px; padding: 4px 8px; min-height: 22px;
    selection-background-color: __COLOR_activeBackground__;
}
QFrame#furnishingQuickSearch {
    background: __COLOR_windowBackground__; border: 1px solid __COLOR_menuBorder__;
}
QFrame#furnishingQuickSearch QLabel { background: transparent; }
QFrame#furnishingQuickSearch QLabel#menuShortcutLabel { color: __COLOR_mutedText__; font-size: 8pt; }
QFrame#furnishingQuickSearchField {
    background: __COLOR_fieldBackground__; border: 1px solid __COLOR_border__; border-radius: 4px;
}
QFrame#furnishingQuickSearchField QLineEdit#furnishingSearch {
    background: transparent; border: none; padding: 4px 0;
}
QListWidget#furnishingQuickResults, QListWidget#furnishingCatalogList {
    background: transparent; color: __COLOR_text__; border: none; outline: none;
}
QListWidget#furnishingQuickResults::item, QListWidget#furnishingCatalogList::item { padding: 0 10px; border-radius: 4px; }
QListWidget#furnishingQuickResults::item:hover,
QListWidget#furnishingQuickResults::item:selected,
QListWidget#furnishingCatalogList::item:hover,
QListWidget#furnishingCatalogList::item:selected {
    background: __COLOR_activeBackground__; color: __COLOR_activeText__;
}
QPlainTextEdit#labelTextField {
    border-radius: 4px; padding: 6px; selection-background-color: __COLOR_activeBackground__;
}
QSlider { min-height: 18px; }
QDoubleSpinBox#settingsValue, QSpinBox#settingsValue { padding-right: 22px; }
QDoubleSpinBox#settingsValue::up-button, QDoubleSpinBox#settingsValue::down-button,
QSpinBox#settingsValue::up-button, QSpinBox#settingsValue::down-button {
    background: __COLOR_controlBackground__; border-left: 1px solid __COLOR_controlBackground__; width: 20px;
}
QDoubleSpinBox#settingsValue::up-button, QSpinBox#settingsValue::up-button { border-top-right-radius: 4px; border-bottom: 1px solid __COLOR_controlBackground__; }
QDoubleSpinBox#settingsValue::down-button, QSpinBox#settingsValue::down-button { border-bottom-right-radius: 4px; }
QDoubleSpinBox#settingsValue::up-button:hover, QDoubleSpinBox#settingsValue::down-button:hover,
QSpinBox#settingsValue::up-button:hover, QSpinBox#settingsValue::down-button:hover { background: __COLOR_hoverBackground__; }
QDoubleSpinBox#settingsValue::up-arrow, QSpinBox#settingsValue::up-arrow { image: url("__ICON_arrow_drop_up__"); width: 16px; height: 16px; }
QDoubleSpinBox#settingsValue::down-arrow, QSpinBox#settingsValue::down-arrow { image: url("__ICON_arrow_drop_down__"); width: 16px; height: 16px; }
QDoubleSpinBox#settingsValue::up-arrow:disabled, QSpinBox#settingsValue::up-arrow:disabled { image: url("__ICON_arrow_drop_up_disabled__"); }
QDoubleSpinBox#settingsValue::down-arrow:disabled, QSpinBox#settingsValue::down-arrow:disabled { image: url("__ICON_arrow_drop_down_disabled__"); }
QSlider::groove:horizontal { height: 6px; background: __COLOR_hoverBackground__; border-radius: 3px; }
QSlider::sub-page:horizontal { background: __COLOR_hoverBackground__; border-radius: 3px; }
QSlider#referenceImageOpacity::sub-page:horizontal:enabled { background: __COLOR_activeBackground__; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; border-radius: 8px; background: __COLOR_sliderHandle__; }
QLabel:disabled { color: __COLOR_disabled__; }
QSlider::groove:horizontal:disabled,
QSlider::sub-page:horizontal:disabled { background: __COLOR_disabledBackground__; }
QSlider::handle:horizontal:disabled { background: __COLOR_disabled__; }
QSlider#measurementMode::groove:vertical { width: 6px; background: __COLOR_hoverBackground__; border-radius: 3px; }
QSlider#measurementMode::handle:vertical { height: 16px; margin: 0 -5px; border-radius: 8px; background: __COLOR_sliderHandle__; }
QSlider#measurementMode::groove:vertical:disabled { background: __COLOR_disabledBackground__; }
QSlider#measurementMode::handle:vertical:disabled { background: __COLOR_disabled__; }
QTabWidget::pane {
    border: 1px solid __COLOR_controlBackground__;
    border-radius: 5px;
    top: -1px;
}
QTabBar::tab {
    background: __COLOR_controlBackground__;
    border: 1px solid __COLOR_controlBackground__;
    padding: 10px 14px;
    min-height: 24px;
    font-size: 14px;
    font-weight: 600;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    color: __COLOR_mutedText__;
}
QTabBar#sidebarTabBar::tab { padding: 6px 14px; min-height: 32px; }
QTabBar::tab:selected {
    background: __COLOR_activeBackground__;
    border-color: __COLOR_activeBackground__;
    color: __COLOR_activeText__;
}
QTabBar::tab:selected:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; }
QTabBar#sidebarTabBar::tab:last { background: __COLOR_hoverBackground__; border-color: __COLOR_hoverBackground__; color: __COLOR_text__; }
QTabBar#sidebarTabBar::tab:last:selected { background: __COLOR_activeBackground__; border-color: __COLOR_activeBackground__; color: __COLOR_activeText__; }
QTabBar#sidebarTabBar::tab:last:selected:hover { background: __COLOR_activeHoverBackground__; border-color: __COLOR_activeHoverBackground__; }
QSplitter::handle { background: __COLOR_windowBackground__; }
QSplitter::handle:hover { background: __COLOR_border__; }
QSplitter#sidebarContentSplitter::handle:vertical { background: __COLOR_controlBackground__; }
QSplitter#sidebarContentSplitter::handle:vertical:hover { background: __COLOR_scrollbarHandle__; }
QScrollBar:vertical { background: __COLOR_windowBackground__; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: __COLOR_scrollbarHandle__; min-height: 24px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: __COLOR_activeBackground__; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip {
    background: __COLOR_controlBackground__;
    color: __COLOR_text__;
    border: 1px solid __COLOR_border__;
    padding: 5px;
}
"""
    style = style.replace("__FONT_FAMILY__", fontFamily)
    for name in ("radio_button_checked", "radio_button_unchecked", "radio_button_halfchecked", "arrow_drop_up", "arrow_drop_down"):
        style = style.replace("__ICON_" + name + "__", UiIconPath(name).as_posix())
        style = style.replace("__ICON_" + name + "_disabled__", UiIconPath(name, themeColors["disabled"]).as_posix())
    return re.sub(r"__COLOR_(\w+)__", lambda match: themeColors[match.group(1)], style)


def HeaderIcon(iconName):
    iconFiles = {
        "Check": "check.svg",
        "Snap": "magnet.svg",
        "Snapping Options": "magnet_config.svg",
        "Group Toggle": "group_toggle.svg",
        "Group": "group.svg",
        "Ungroup": "ungroup.svg",
        "Chair": "chair.svg",
        "Construction": "construction.svg",
        "Viewport": "crop_3_2.svg", "Appearance": "palette.svg",
        "Measurements": "measure.svg",
        "Walls": "wall_2.svg",
        "File": "insert_drive_file.svg",
        "Objects": "object.svg",
        "Image": "image.svg",
        "Edit": "edit.svg",
        "Transform": "translate.svg",
        "View": "visibility.svg",
        "Export": "save_alt_24dp_E3E3E3.svg",
        "Maximize": "fullscreen.svg",
        "Hide selected": "hide_sel.svg",
        "Hide unselected": "hide_unsel.svg",
        "Unhide": "unhide.svg",
        "Settings": "settings.svg",
        "Help": "help.svg",
        "New Project": "file_new.svg",
        "Open Project": "file_open.svg",
        "Revert": "refresh.svg",
        "Save Project": "save.svg",
        "Save Project as": "save_as.svg",
        "Close Project": "close.svg",
        "Undo": "undo.svg",
        "Redo": "redo.svg",
        "Cut": "content_cut.svg",
        "Copy": "content_copy.svg",
        "Paste": "content_paste.svg",
        "About": "info.svg",
    }
    return UiIcon(iconFiles[iconName].removesuffix(".svg"))
