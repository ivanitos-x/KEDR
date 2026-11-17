"""Native GPU integration check: run separately without QT_QPA_PLATFORM=offscreen."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize,QPoint,Qt,QPointF,QTimer
from PySide6.QtTest import QTest
from PySide6.QtGui import QWheelEvent,QContextMenuEvent
from viewers.png import load_glb,SolidRenderer,PngWindow
from test_glb import fixture
app=QApplication([])
out=Path(__file__).resolve().parents[1]/'.test-tmp'
out.mkdir(exist_ok=True)
path=out/'two objects.glb'; fixture(path)
vertices,info=load_glb(path)
renderer=SolidRenderer(vertices)
image=renderer.render(QSize(400,400),0,0,1)
assert image.pixelColor(0,0).alpha()==0
alphas=[image.pixelColor(x,y).alpha() for y in range(400) for x in range(400)]
assert max(alphas)==255 and any(0<a<255 for a in alphas), 'Missing geometry / antialiasing'
assert image!=renderer.render(QSize(400,400),30,20,1)
image.save(str(out/'solid.png'))
renderer.close()
window=PngWindow(path); window.show(); app.processEvents()
QTest.mousePress(window,Qt.MouseButton.LeftButton,pos=QPoint(200,200))
QTest.mouseMove(window,QPoint(250,230)); QTest.mouseRelease(window,Qt.MouseButton.LeftButton,pos=QPoint(250,230)); QTest.qWait(30)
assert window.isVisible() and window.yaw!=0
angle=window.yaw; origin=window.pos()
QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=QPoint(200,200))
QTest.mouseMove(window,QPoint(230,240)); QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=QPoint(230,240))
assert window.isVisible() and window.pos()!=origin and window.yaw==angle
event=QWheelEvent(QPointF(200,200),QPointF(200,200),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
window.wheelEvent(event); assert window.zoom>1
QTimer.singleShot(30,lambda: app.activePopupWidget().close() if app.activePopupWidget() else None)
window.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse,QPoint(200,200),window.mapToGlobal(QPoint(200,200))))
second=PngWindow(path); second.show(); app.processEvents(); assert second.isVisible()
second.close(); assert window.isVisible()
window.activateWindow(); app.processEvents()
QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=QPoint(200,200))
assert not window.isVisible()
assert window.renderer is None
print('Native OpenGL: RGBA, MSAA, rotation, Shift move, zoom, menu, independent windows, click close, cleanup OK',info)
