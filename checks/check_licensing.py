"""Source and future binary packages carry the same complete licensing documents."""
import ast
from pathlib import Path


def Main():
    root = Path(__file__).resolve().parents[1]
    app = root / "planner-main"
    copying = (app / "COPYING").read_bytes()
    assert (root / "LICENSE").read_bytes() == copying, "Repository/app GPL copies disagree"
    text = copying.decode("utf-8").replace("\r\n", "\n")
    assert text.startswith("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007")
    assert len(copying) > 30000 and "END OF TERMS AND CONDITIONS" in text
    tree = ast.parse((root / "tools/Planner.spec").read_text(encoding = "utf-8"))
    licenseFiles = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "licenseFiles" for target in node.targets))
    expected = {"COPYING", "ASSET_LICENSE.txt", "BRANDING_LICENSE.txt", "LICENSES.txt"}
    assert set(licenseFiles) == expected
    assert all((app / name).is_file() for name in licenseFiles), "A packaged license is missing"
    notices = (app / "LICENSES.txt").read_text(encoding = "utf-8")
    assert all(name in notices for name in expected - {"LICENSES.txt"})
    assert "GPL-3.0-only" in notices
    print("Licensing: complete matching GPL texts, separate asset/branding terms and binary-package inclusion passed")


if __name__ == "__main__":
    Main()
