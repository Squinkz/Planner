"""Reference image failures identify invalid data, dimension limits and decoder memory limits."""
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from planner_app.reference_image import ReadReferenceImage
from fixtures.parity_examples import ExampleWindow


def Main():
    cases = ((QtCore.QSize(0, 0), "Unsupported image format", ("dimensions", "damaged", "unsupported")),
             (QtCore.QSize(40000, 100), "Unknown error", ("40,000 × 100", "32,767", "Resize")),
             (QtCore.QSize(12000, 10000), "Unknown error", ("12,000 × 10,000", "120.0 million", "100 million", "Resize")),
             (QtCore.QSize(9000, 9000), "Unable to allocate image", ("9,000 × 9,000", "memory", "256 MiB", "Resize")),
             (QtCore.QSize(9000, 9000), "Unknown error", ("9,000 × 9,000", "memory", "256 MiB")),
             (QtCore.QSize(100, 100), "Corrupt PNG data", ("Cannot read reference image", "Corrupt PNG data")))
    with ExampleWindow() as (main, folder):
        path = folder / "reference.png"
        image = QtGui.QImage(100, 50, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("red"))
        assert image.save(str(path))
        assert main.referenceImage.Load(path)
        before = main.referenceImage.Snapshot()
        for size, error, expected in cases:
            reader = Mock()
            reader.size.return_value = size
            reader.errorString.return_value = error
            reader.allocationLimit.return_value = 256
            reader.read.return_value = QtGui.QImage()
            with patch("planner_app.reference_image.QtGui.QImageReader", return_value = reader):
                try:
                    ReadReferenceImage(b"test")
                except ValueError as failure:
                    message = str(failure)
                else:
                    raise AssertionError("Invalid reference image accepted")
                assert all(text in message for text in expected), message
                if size.width() <= 0 or size.width() > 32767 or size.width() * size.height() > 100000000:
                    reader.read.assert_not_called()
                with patch.object(main, "ShowAppMessage") as notice:
                    assert not main.referenceImage.Load(path)
                assert notice.call_args.args == ("Cannot Load Reference Image", message)
                assert notice.call_args.kwargs == {"kind": "warning"}
                assert main.referenceImage.Snapshot() == before
                assert main.referenceImage.active
        try:
            ReadReferenceImage(b"not an image")
        except ValueError as failure:
            assert "unsupported format" in str(failure)
        else:
            raise AssertionError("Invalid image accepted")
    print("PASS: actionable reference image errors and failed replacement preserves the loaded image")


if __name__ == "__main__":
    Main()
