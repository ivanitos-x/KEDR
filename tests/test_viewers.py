import json
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sqlite3
import tempfile
tempfile.tempdir = str(Path(__file__).resolve().parents[1] / '.test-tmp')
Path(tempfile.tempdir).mkdir(exist_ok=True)
import unittest
from unittest.mock import patch
from viewers import core
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from viewers.png import PngWindow

APP = QApplication.instance() or QApplication([])

class ViewerTests(unittest.TestCase):
    def test_alpha_mask_retains_partial_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'alpha.png'
            img=QImage(3,1,QImage.Format.Format_ARGB32)
            for x,a in enumerate([0,64,255]): img.setPixelColor(x,0,QColor(255,0,0,a))
            img.save(str(p))
            win=PngWindow(p)
            self.assertFalse(win.mask().contains(QPoint(0,0)))
            self.assertTrue(win.mask().contains(QPoint(1,0)))
            self.assertEqual(win.image.pixelColor(1,0).alpha(),64)
            win.close()
            p=Path(tmp)/'opaque.png'; img=QImage(2,2,QImage.Format.Format_RGB32); img.fill(QColor('white')); img.save(str(p))
            win=PngWindow(p); self.assertTrue(win.mask().isEmpty()); win.close()

    def test_click_closes_drag_keeps_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gesture.png'
            img=QImage(150,150,QImage.Format.Format_RGB32); img.fill(QColor('red')); img.save(str(path))
            win=PngWindow(path); win.show(); APP.processEvents()
            QTest.mousePress(win,Qt.MouseButton.LeftButton,pos=QPoint(20,20))
            QTest.mouseMove(win,QPoint(60,60))
            QTest.mouseRelease(win,Qt.MouseButton.LeftButton,pos=QPoint(60,60))
            self.assertTrue(win.isVisible())
            QTest.mouseClick(win,Qt.MouseButton.LeftButton,pos=QPoint(30,30))
            self.assertFalse(win.isVisible())

    def test_background_click_and_middle_drag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gesture.png'
            image=QImage(150,150,QImage.Format.Format_RGB32)
            image.fill(QColor('red'))
            self.assertTrue(image.save(str(path)))
            win=PngWindow(path)
            other=PngWindow(path)
            win.show()
            other.show()
            other.activateWindow()
            APP.processEvents()
            self.assertFalse(win.isActiveWindow())
            QTest.mouseClick(win,Qt.MouseButton.LeftButton,pos=QPoint(20,20))
            self.assertTrue(win.isVisible())
            original=win.pos()
            QTest.mousePress(win,Qt.MouseButton.MiddleButton,pos=QPoint(20,20))
            QTest.mouseMove(win,QPoint(60,60))
            QTest.mouseRelease(win,Qt.MouseButton.MiddleButton,pos=QPoint(60,60))
            self.assertEqual(win.pos(),original+QPoint(40,40))
            QTest.mouseClick(win,Qt.MouseButton.MiddleButton,pos=QPoint(30,30))
            self.assertTrue(win.isVisible())
            win.activateWindow()
            APP.processEvents()
            QTest.mouseClick(win,Qt.MouseButton.LeftButton,pos=QPoint(30,30))
            self.assertFalse(win.isVisible())
            other.close()

if __name__=='__main__': unittest.main()
