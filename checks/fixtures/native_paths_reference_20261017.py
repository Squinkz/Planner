"""Load frozen pre-backend modules with their original package-relative imports."""
from pathlib import Path
import importlib.util
import sys
folder = Path(__file__).with_suffix("")
modules = {}


def Load(name):
    if name not in modules:
        package, leaf = name.split("/")
        fullName = "planner_app." + package + "._native_reference_" + leaf.removesuffix(".py")
        spec = importlib.util.spec_from_file_location(fullName, folder / name.replace("/", "_"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[fullName] = module
        source = (folder / name.replace("/", "_")).read_text(encoding = "utf-8")
        for old, new in [("from .furnishing_mask import", "from ._native_reference_furnishing_mask import"),
                         ("from .edit_cache import", "from ._native_reference_edit_cache import"),
                         ("from planner_app.graphics.arrows import", "from planner_app.graphics._native_reference_arrows import"),
                         ("from planner_app.graphics.object_composite import", "from planner_app.graphics._native_reference_object_composite import")]:
            source = source.replace(old, new)
        exec(compile(source, str(folder / name.replace("/", "_")), "exec"), module.__dict__)
        modules[name] = module
    return modules[name]


def Configure():
    arrows = Load("graphics/arrows.py")
    masks = Load("graphics/furnishing_mask.py")
    objects = Load("graphics/object_composite.py")
    objects.BackgroundPathEngine = masks.BackgroundPathEngine
    geometry = Load("viewport/geometry.py")
    geometry.ArrowPaths = arrows.ArrowPaths
    Load("viewport/edit_cache.py")
    rendering = Load("viewport/rendering.py")
    rendering.ArrowPaths = arrows.ArrowPaths
    rendering.ObjectPaintDevice = objects.ObjectPaintDevice
    return modules


def ReferenceViewport():
    from planner_app.viewport.widget import DrawingViewport
    Configure()
    class FrozenViewport(DrawingViewport):
        pass
    for moduleName, className in [("viewport/geometry.py", "GeometryMixin"),
        ("viewport/scene.py", "SceneEditingMixin"), ("viewport/snapping.py", "SnappingMixin"),
        ("viewport/edit_cache.py", "EditPaintCacheMixin"), ("viewport/rendering.py", "RenderingMixin")]:
        for name, value in vars(getattr(Load(moduleName), className)).items():
            if callable(value) and not name.startswith("__"):
                setattr(FrozenViewport, name, value)
    return FrozenViewport
