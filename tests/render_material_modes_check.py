"""Self-contained native GPU test: two material slots, menu and rotation."""
from pathlib import Path
import sys
import faulthandler
faulthandler.dump_traceback_later(8,exit=True)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMenu
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from viewers.visual.contracts import MaterialData,MaterialOp
from viewers.visual.bootstrap import open_asset,create_presentation
from viewers.png import PngWindow
from viewers import png
from blend_fixture import blend_fixture

app=QApplication([])
errors=[]
png.error=lambda parent,exc:errors.append(str(exc))
root=Path(__file__).resolve().parents[1]/'.test-tmp'; root.mkdir(exist_ok=True)
path=root/'two materials.blend'; blend_fixture(path,True)
asset=open_asset(path)
def material(name,color): return MaterialData(name,(MaterialOp('constant',values=color),MaterialOp('constant',values=(.5,)*4),MaterialOp('constant',values=(0,)*4)),0,1,2)
data=replace(asset.data,materials=(material('red',(1,0,0,1)),material('blue',(0,0,1,1))),material_ids=(0,)*12+(1,)*12)
asset=replace(asset,data=data,capabilities=asset.capabilities|{'view.materials'})
image,renderer=create_presentation(asset); renderer.set_display_mode('materials')
frame=renderer.render(image.size(),0,0,1)
red=blue=0
for y in range(0,frame.height(),4):
    for x in range(0,frame.width(),4):
        c=frame.pixelColor(x,y)
        if c.alpha()!=255: continue
        red+=c.red()>c.blue()*2; blue+=c.blue()>c.red()*2
assert red>100 and blue>100,(red,blue)
renderer.close(); renderer.close()
win=PngWindow(path,asset); win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen); win.show()
def inspect_menu(menu,*args):
    actions=menu.actions()
    modes=next(a.menu() for a in actions if a.text()=='Режим отображения')
    assert [a.text() for a in modes.actions()]==['Solid','Материалы (приближённо)','PBR']
    modes.actions()[1].trigger(); assert win.display_mode=='materials'
    auto=next(a for a in actions if a.text().startswith('Автоматическое вращение'))
    auto.trigger()
inspect_menu(win.create_context_menu())
assert not errors,errors
assert win.auto_rotation
QTest.qWait(180); assert win.yaw>0
win.press=QPoint(1,1); angle=win.yaw; QTest.qWait(100); assert win.yaw==angle
win.press=None; win.toggle_auto_rotation(False)
angle=win.yaw; QTest.qWait(70); assert win.yaw==angle
win.close(); assert not win.auto_timer.isActive()
assert not errors,errors
print('Native material slots, context mode actions, auto rotate, drag pause and stop/cleanup OK')
faulthandler.cancel_dump_traceback_later()
