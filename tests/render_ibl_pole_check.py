"""Regression: an infinitesimal normal change must not rotate IBL samples abruptly."""
from pathlib import Path
import sys,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from array import array
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from viewers.visual.contracts import SceneData,MaterialData,MaterialOp
from viewers.visual.renderers.pbr import PbrRenderer
app=QApplication([])
material=MaterialData('smooth metal',(MaterialOp('constant',values=(.5,.5,.5,1)),MaterialOp('constant',values=(.8,)*4),MaterialOp('constant',values=(1,)*4)),0,1,2)
def sample(x):
    vertices=array('f'); normal=(x,0,math.sqrt(1-x*x))
    for p in [(-1,-1,0),(1,-1,0),(1,1,0),(-1,-1,0),(1,1,0),(-1,1,0)]: vertices.extend((*p,*normal))
    scene=SceneData(vertices.tobytes(),{},(material,),(0,0),bytes(72)); renderer=PbrRenderer(scene)
    try:
        renderer.set_display_mode('pbr'); c=renderer.render(QSize(64,64),0,0,1).pixelColor(32,32)
        return c.red(),c.green(),c.blue()
    finally: renderer.close()
a,b=sample(.04470),sample(.04472)
delta=max(abs(x-y) for x,y in zip(a,b))
print('IBL pole threshold samples:',a,b,'max channel delta:',delta)
assert delta<=2, 'Discontinuous IBL sample basis at normal.z=0.999'
