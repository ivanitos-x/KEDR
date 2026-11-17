"""Native GPU/material/autorotation integration; optional user BLEND path argument."""
from pathlib import Path
import hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from viewers.visual.bootstrap import open_asset,create_presentation
from viewers.png import PngWindow

app=QApplication([])
path=Path(sys.argv[1]); before=hashlib.sha256(path.read_bytes()).hexdigest()
with patch('subprocess.Popen',side_effect=AssertionError('Blender is forbidden')):
    asset=open_asset(path)
    assert 'view.materials' in asset.capabilities
    assert len(asset.data.materials[0].nodes)>3,asset.data.materials[0].notices
    solid,renderer=create_presentation(asset)
    renderer.set_display_mode('materials')
    frame=renderer.render(solid.size(),30,15,1)
    assert frame!=solid
    assert frame.pixelColor(0,0).alpha()==0
    colors={frame.pixelColor(x,y).rgb() for x in range(0,frame.width(),4) for y in range(0,frame.height(),4) if frame.pixelColor(x,y).alpha()==255}
    assert len(colors)>100,('Missing procedural variation',len(colors))
    output=Path(__file__).resolve().parents[1]/'.test-tmp'
    frame.save(str(output/'material-preview.png'))
    renderer.set_display_mode('solid'); assert solid==renderer.render(solid.size(),0,0,1)
    renderer.close()
    win=PngWindow(path,asset); win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen); win.show()
    win.toggle_auto_rotation(True); QTest.qWait(200); assert win.yaw>0
    win.toggle_auto_rotation(False); angle=win.yaw; QTest.qWait(100); assert win.yaw==angle
    win.set_display_mode('materials'); assert win.display_mode=='materials'
    win.toggle_auto_rotation(True); win.hide(); assert not win.auto_timer.isActive()
    win.show(); assert win.auto_timer.isActive()
    win.close(); assert not win.auto_timer.isActive()
assert hashlib.sha256(path.read_bytes()).hexdigest()==before
print('Materials on surface / mode switch / autorotation / hide-close cleanup / unchanged input OK',asset.info,'unique sampled colors:',len(colors))
