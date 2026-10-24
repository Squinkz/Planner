"""Bundled runtime resources and executable-relative editable data."""

from pathlib import Path
import sys


appDirectory = Path(__file__).resolve().parent.parent
externalDirectory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else appDirectory
assetsDirectory = appDirectory / "assets"
furnishingsDirectory = externalDirectory / "furnishings"
fontsDirectory = externalDirectory / "assets" / "fonts"
themesDirectory = externalDirectory / "themes"
texturesDirectory = externalDirectory / "textures"
helpDirectory = externalDirectory / "docs" / "help"
