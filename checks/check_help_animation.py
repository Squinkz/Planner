"""Native GIF frames repaint in Help without changing layout or navigation."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, WorkflowState


def Main():
    with ExampleWindow() as (main, folder):
        before = WorkflowState(main)
        main.ShowHelp("drawing.md")
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        helpWindow = main.helpWindow
        browser = helpWindow.browser
        block = browser.document().begin()
        names = []
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().isImageFormat():
                    names.append(fragment.charFormat().toImageFormat().name())
                iterator += 1
            block = block.next()
        gifNames = {name.replace("\\", "/") for name in names if name.lower().endswith(".gif")}
        assert len(helpWindow.imageAnimations) == len(gifNames) and gifNames
        movie = next(iter(helpWindow.imageAnimations.values()))["movie"]
        assert movie.frameCount() > 1 and movie.cacheMode() == QtGui.QMovie.CacheMode.CacheNone
        assert movie.state() == QtGui.QMovie.MovieState.Running
        cursor = browser.document().find("Walls")
        browser.setTextCursor(cursor)
        frame = movie.currentFrameNumber()
        image = browser.viewport().grab().toImage()
        source, history = browser.source(), browser.backwardHistoryCount()
        scroll = browser.verticalScrollBar().value()
        size = browser.document().size()
        for unused in range(40):
            QtTest.QTest.qWait(50)
            if movie.currentFrameNumber() != frame:
                break
        assert movie.currentFrameNumber() != frame
        assert browser.viewport().grab().toImage() != image, "Movie advanced without repainting the embedded GIF"
        assert browser.source() == source and browser.backwardHistoryCount() == history
        assert browser.textCursor().selectedText() == cursor.selectedText()
        assert browser.verticalScrollBar().value() == scroll and browser.document().size() == size

        helpWindow.showMinimized()
        app.processEvents()
        assert movie.state() == QtGui.QMovie.MovieState.Paused
        frame = movie.currentFrameNumber()
        QtTest.QTest.qWait(150)
        assert movie.currentFrameNumber() == frame
        helpWindow.showNormal()
        app.processEvents()
        assert movie.state() == QtGui.QMovie.MovieState.Running
        QtTest.QTest.qWait(max(200, movie.nextFrameDelay() + 100))
        assert movie.currentFrameNumber() != frame

        helpWindow.resize(440, 500)
        app.processEvents()
        helpWindow.ResizeImages()
        QtTest.QTest.qWait(150)
        assert browser.horizontalScrollBar().maximum() == 0
        helpWindow.ShowPage("README.md")
        assert not helpWindow.imageAnimations
        helpWindow.backButton.click()
        assert len(helpWindow.imageAnimations) == len(gifNames)

        # Multiple references to the same file share one decoder. Use the same
        # ordinary Markdown image syntax as a real help page.
        helpWindow.StopAnimations()
        browser.document().setMarkdown("![First](images/wall_tool.gif)\n\n![Second](images/wall_tool.gif)")
        helpWindow.LoadAnimations()
        assert len(helpWindow.imageAnimations) == 1
        assert len(next(iter(helpWindow.imageAnimations.values()))["positions"]) == 2
        helpWindow.close()
        assert not helpWindow.imageAnimations
        assert WorkflowState(main) == before
    print("Help GIFs: natural playback/repaint, stable layout/history, shared decoding, pause/resume and cleanup passed")


if __name__ == "__main__":
    Main()
