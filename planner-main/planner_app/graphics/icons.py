"""Neutral UI SVGs, semantic paint colors and cached stylesheet image paths."""
import re
import logging
import tempfile
import weakref
from collections import OrderedDict
from itertools import count
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.paths import assetsDirectory
from .palette import themeColors as uiIconColors


iconSources = {}
pixmapSources = {}
# Retain one engine per semantic artwork/palette. Return wrappers sharing that
# engine so Qt-held copies keep their source lookup and detach safely on edits.
themeIconCache = OrderedDict()
iconWrappers = weakref.WeakSet()
iconPaths = {}
artworkCacheLimit = 512
sourceCacheLimit = 2048
pathCacheLimit = 1024
pruneRequests = 0
iconFileIds = count()
unavailableIconWarnings = set()
logger = logging.getLogger(__name__)


def PruneArtworkCaches(force = True):
    """Retire unused variants, preserving sources held by Python and live Qt UI."""
    while len(themeIconCache) > artworkCacheLimit:
        themeIconCache.popitem(last = False)
    global pruneRequests
    pruneRequests += 1
    if not force and pruneRequests % 256:
        return
    liveIcons = {icon.cacheKey() for icon in iconWrappers}
    livePixmaps = set()
    livePaths = set()
    app = QtWidgets.QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            liveIcons.add(widget.windowIcon().cacheKey())
            if hasattr(widget, "icon"):
                liveIcons.add(widget.icon().cacheKey())
            if isinstance(widget, QtWidgets.QLabel):
                pixmap = widget.pixmap()
                if pixmap is not None:
                    livePixmaps.add(pixmap.cacheKey())
            if isinstance(widget, (QtWidgets.QComboBox, QtWidgets.QTabWidget, QtWidgets.QTabBar)):
                for index in range(widget.count()):
                    icon = widget.itemIcon(index) if isinstance(widget, QtWidgets.QComboBox) else widget.tabIcon(index)
                    liveIcons.add(icon.cacheKey())
            if isinstance(widget, QtWidgets.QTreeWidget):
                iterator = QtWidgets.QTreeWidgetItemIterator(widget)
                while iterator.value() is not None:
                    item = iterator.value()
                    for column in range(widget.columnCount()):
                        liveIcons.add(item.icon(column).cacheKey())
                    iterator += 1
            for action in widget.actions():
                liveIcons.add(action.icon().cacheKey())
            for stylesheetPath in re.findall(r'url\(["\']?([^"\')]+)', widget.styleSheet()):
                livePaths.add(Path(stylesheetPath).as_posix())
        for stylesheetPath in re.findall(r'url\(["\']?([^"\')]+)', app.styleSheet()):
            livePaths.add(Path(stylesheetPath).as_posix())
    # Keep recently returned standalone sources as well as all known live UI.
    for registry, live in ((iconSources, liveIcons), (pixmapSources, livePixmaps)):
        recent = set(list(registry)[-sourceCacheLimit:])
        for key in list(registry):
            if key not in live and key not in recent:
                del registry[key]
    for key in list(iconPaths):
        if key not in iconSources:
            del iconPaths[key]
        else:
            livePaths.update(path.as_posix() for path in iconPaths[key])
    recentPaths = set(list(uiIconCache)[-pathCacheLimit:])
    for key, path in list(uiIconCache.items()):
        if key not in recentPaths and path.as_posix() not in livePaths:
            path.unlink(missing_ok = True)
            del uiIconCache[key]


class ThemeIcon(QtGui.QIcon):
    """Retain paint sources for live refresh, including copies held by Qt widgets."""
    def __init__(self, source, factory):
        super().__init__(source)
        self.factory = factory
        self.sourcePaths = getattr(source, "sourcePaths", ())
        iconWrappers.add(self)
        iconPaths[self.cacheKey()] = self.sourcePaths
        iconSources[self.cacheKey()] = factory

    def pixmap(self, *args):
        pixmap = super().pixmap(*args)
        pixmapSources[pixmap.cacheKey()] = (self.factory, args)
        if len(pixmapSources) > sourceCacheLimit * 2:
            PruneArtworkCaches(force = False)
        return pixmap


uiIconCache = OrderedDict()
uiIconCacheDirectory = None


def UiIconPath(iconName, color = None, rotation = 0):
    """Tint once per palette/color; Qt stylesheets can share these temporary SVGs."""
    global uiIconCacheDirectory
    color = QtGui.QColor(color).name() if color is not None else None
    cacheKey = (iconName, color, rotation, tuple(uiIconColors.items()))
    if cacheKey in uiIconCache:
        uiIconCache.move_to_end(cacheKey)
        return uiIconCache[cacheKey]
    sourcePath = assetsDirectory / "icons_ui" / (iconName + ".svg")
    try:
        root = ElementTree.fromstring(sourcePath.read_bytes())
    except (OSError, ElementTree.ParseError) as error:
        if sourcePath not in unavailableIconWarnings:
            logger.warning("Could not load UI icon %s: %s. Using an empty icon.", sourcePath, error)
            unavailableIconWarnings.add(sourcePath)
        # A valid transparent SVG works for both QIcon and stylesheet URL users,
        # including disabled states, without repeated Qt SVG warnings.
        root = ElementTree.Element("svg", xmlns = "http://www.w3.org/2000/svg",
                                   width = "24", height = "24", viewBox = "0 0 24 24")
    paintPattern = re.compile(r"(\b(fill|stroke|color|stop-color)\s*:\s*)([^;}]+)", re.IGNORECASE)

    def Recolor(attribute, paint, element):
        if paint.strip().lower() in ("none", "transparent", "inherit") or paint.strip().startswith("url("):
            return paint
        role = element.get("data-theme-" + attribute, "icon")
        return color if color is not None and role not in ("canvas", "shadow") else uiIconColors[role]

    for element in root.iter():
        for attribute in ("fill", "stroke", "color", "stop-color"):
            if attribute in element.attrib:
                element.set(attribute, Recolor(attribute, element.get(attribute), element))
        styleElement = element.tag.rsplit("}", 1)[-1] == "style"
        style = element.text if styleElement else element.get("style")
        if style:
            style = paintPattern.sub(lambda match: match.group(1) + Recolor(match.group(2).lower(), match.group(3), element), style)
            if styleElement:
                element.text = style
            else:
                element.set("style", style)
    root.set("fill", root.get("fill", color or uiIconColors["icon"]))
    if rotation:
        x, y, width, height = map(float, root.get("viewBox", "0 0 24 24").replace(",", " ").split())
        group = ElementTree.Element("{http://www.w3.org/2000/svg}g",
                                    transform = f"rotate({rotation} {x + width / 2} {y + height / 2})")
        for child in list(root):
            root.remove(child)
            group.append(child)
        root.append(group)
    if uiIconCacheDirectory is None:
        uiIconCacheDirectory = tempfile.TemporaryDirectory(prefix = "planner-ui-icons-")
    path = Path(uiIconCacheDirectory.name) / f"icon-{next(iconFileIds)}.svg"
    path.write_bytes(ElementTree.tostring(root))
    uiIconCache[cacheKey] = path
    if len(uiIconCache) > pathCacheLimit * 2:
        PruneArtworkCaches(force = False)
    return path


def UiIcon(iconName, color = None, rotation = 0):
    """Keep SVG icons scalable while sharing the same cache as stylesheet controls."""
    role = next((key for key, value in uiIconColors.items() if value == color), None) if color is not None else None
    cacheKey = ("ui", iconName, role, color, rotation, tuple(uiIconColors.items()))
    cached = themeIconCache.get(cacheKey)
    if cached is not None:
        themeIconCache.move_to_end(cacheKey)
        return ThemeIcon(cached, cached.factory)
    factory = lambda: UiIcon(iconName, uiIconColors[role] if role else color, rotation = rotation)
    icon = ThemeIcon(str(UiIconPath(iconName, color, rotation = rotation)), factory)
    disabledPath = str(UiIconPath(iconName, uiIconColors["iconDisabled"], rotation = rotation))
    for state in (QtGui.QIcon.State.Off, QtGui.QIcon.State.On):
        icon.addFile(disabledPath, QtCore.QSize(), QtGui.QIcon.Mode.Disabled, state)
    iconSources[icon.cacheKey()] = factory
    icon.sourcePaths = (UiIconPath(iconName, color, rotation = rotation), Path(disabledPath))
    iconPaths[icon.cacheKey()] = icon.sourcePaths
    themeIconCache[cacheKey] = icon
    if len(themeIconCache) > artworkCacheLimit:
        PruneArtworkCaches(force = False)
    return icon


def GroupModeIcon():
    cacheKey = ("group-mode", tuple(uiIconColors.items()))
    cached = themeIconCache.get(cacheKey)
    if cached is not None:
        themeIconCache.move_to_end(cacheKey)
        return ThemeIcon(cached, cached.factory)
    icon = ThemeIcon(str(UiIconPath("group_toggle_off")), GroupModeIcon)
    for state, name in ((QtGui.QIcon.State.Off, "group_toggle_off"), (QtGui.QIcon.State.On, "group_toggle")):
        icon.addFile(str(UiIconPath(name)), QtCore.QSize(), QtGui.QIcon.Mode.Normal, state)
        icon.addFile(str(UiIconPath(name, uiIconColors["iconDisabled"])), QtCore.QSize(), QtGui.QIcon.Mode.Disabled, state)
    iconSources[icon.cacheKey()] = GroupModeIcon
    icon.sourcePaths = tuple(UiIconPath(name, color) for name in ("group_toggle_off", "group_toggle")
                             for color in (None, uiIconColors["iconDisabled"]))
    iconPaths[icon.cacheKey()] = icon.sourcePaths
    themeIconCache[cacheKey] = icon
    if len(themeIconCache) > artworkCacheLimit:
        PruneArtworkCaches(force = False)
    return icon
