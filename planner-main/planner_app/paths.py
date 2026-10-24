"""Application-relative resource paths, independent of the working directory."""

from pathlib import Path


appDirectory = Path(__file__).resolve().parent.parent
assetsDirectory = appDirectory / "assets"
furnishingsDirectory = appDirectory / "furnishings"
