"""Self-contained native PBR acceptance: no Blender or external assets."""
from pathlib import Path
import sys,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from array import array
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize,Qt
from PySide6.QtTest import QTest
from viewers.visual.contracts import SceneData,MaterialData,MaterialOp,Asset
from viewers.visual.environment import EnvironmentData
from viewers.visual.bootstrap import build_registry,create_presentation
from viewers.png import PngWindow

app=QApplication([])
def sphere():
    vertices=array('f'); coordinates=array('f')
    def p(theta,phi):return (math.sin(theta)*math.cos(phi),math.cos(theta),math.sin(theta)*math.sin(phi))
    for y in range(12):
        for x in range(24):
            a=p(y*math.pi/12,x*math.pi/12); b=p((y+1)*math.pi/12,x*math.pi/12); c=p((y+1)*math.pi/12,(x+1)*math.pi/12); d=p(y*math.pi/12,(x+1)*math.pi/12)
            for v in (a,b,c,a,c,d): vertices.extend((*v,*v)); coordinates.extend((z+1)/2 for z in v)
    return vertices.tobytes(),coordinates.tobytes()
vertices,coords=sphere(); count=len(vertices)//72
def scene(metal,rough):
    mat=MaterialData('physical',(MaterialOp('constant',values=(.8,.16,.025,1)),MaterialOp('constant',values=(rough,)*4),MaterialOp('constant',values=(metal,)*4)),0,1,2)
    return SceneData(vertices,{'vertices':count*3,'triangles':count,'objects':1,'bytes':len(vertices)},(mat,),(0,)*count,coords)
def render(metal,rough):
    asset=Asset(scene(metal,rough),frozenset({'view.rotate','view.materials'}),scene(metal,rough).info)
    initial,session=create_presentation(asset); session.set_display_mode('pbr')
    try:return session.render(QSize(256,256),15,10,1)
    finally:session.close();session.close()
dielectric=render(0,.15); metal=render(1,.15); rough=render(1,.85)
assert dielectric!=metal and metal!=rough
assert metal.pixelColor(0,0).alpha()==0
assert any(metal.pixelColor(x,y).alpha()==255 for x in range(50,200,10) for y in range(50,200,10))
asset=Asset(scene(.7,.35),frozenset({'view.rotate','view.materials'}),scene(.7,.35).info)
initial,session=create_presentation(asset); session.set_display_mode('pbr')
studio=session.render(QSize(256,256),0,0,1)
env=EnvironmentData(1,1,bytes([180,180,180,130]))
session.set_environment(env); custom=session.render(QSize(256,256),0,0,1)
assert custom!=studio
session.set_display_mode('solid'); assert session.mode=='solid'
session.set_display_mode('pbr'); assert custom==session.render(QSize(256,256),0,0,1)
session.set_environment(None); assert studio==session.render(QSize(256,256),0,0,1)
session.close()
win=PngWindow('synthetic.glb',asset); win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen); win.show()
menu=win.create_context_menu(); modes=next(a.menu() for a in menu.actions() if a.text()=='Режим отображения')
next(a for a in modes.actions() if a.text()=='PBR').trigger(); assert win.display_mode=='pbr'
win.toggle_auto_rotation(True); QTest.qWait(100); assert win.yaw>0; win.close()
root=Path(__file__).resolve().parents[1]/'.test-tmp'
metal.save(str(root/'pbr-metal.png')); rough.save(str(root/'pbr-rough.png'))
print('PBR native: metal/rough response, alpha, HDRI, mode roundtrip, registry QAction, auto rotation and cleanup OK')
