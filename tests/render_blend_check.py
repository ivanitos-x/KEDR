"""Native Windows integration of the modular BLEND path; never runs Blender."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtCore import QSize,QTimer,Qt
from blend_fixture import blend_fixture
from viewers.visual.bootstrap import open_asset,create_presentation
from viewers.visual.contracts import AssetFailure
from viewers import png

app=QApplication([])
root=Path(__file__).resolve().parents[1]/'.test-tmp'; root.mkdir(exist_ok=True)
path=root/'native cube.blend'; blend_fixture(path,True,True)
with patch('subprocess.Popen',side_effect=AssertionError('Blender is forbidden')):
    asset=open_asset(path)
    image,renderer=create_presentation(asset)
    assert image.pixelColor(0,0).alpha()==0
    rotated=renderer.render(image.size(),35,20,1)
    assert image!=rotated
    assert any(rotated.pixelColor(x,y).alpha()==255 for x in range(0,image.width(),10) for y in range(0,image.height(),10))
    rotated.save(str(root/'blend-solid.png'))
    renderer.close(); renderer.close()
    png.open_path(path)
    for _ in range(200):
        QTest.qWait(10)
        if not png.pending_loads: break
    assert not png.pending_loads and len(png.windows)==1
    window=png.windows[0]; assert window.isVisible() and window.model_info['triangles']==24
    window.close()
    def slow(path,context):
        for _ in range(500):
            context.check(); context.cancel.wait(.01)
        raise AssertionError('Cancellation failed')
    with patch('viewers.visual.bootstrap.open_asset',side_effect=slow):
        png.open_path(path); QTest.qWait(20)
        dialog=next(iter(png.pending_loads)); assert dialog.worker.isRunning()
        dialog.close()
        for _ in range(200):
            QTest.qWait(10)
            if not png.pending_loads: break
        assert not png.pending_loads
    # A failed worker must not destroy its error dialog when finished arrives.
    invalid=root/'broken.blend'; invalid.write_bytes(b'BLENDER-v403broken')
    observed=[]
    polls=[0]
    def dismiss_error():
        boxes=[w for w in app.topLevelWidgets() if isinstance(w,QMessageBox) and w.isVisible()]
        observed.extend(box.text() for box in boxes)
        for box in boxes: box.accept()
        polls[0]+=1
        if not boxes and polls[0]<100: QTimer.singleShot(50,dismiss_error)
    class QuietMessageBox(QMessageBox):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    QTimer.singleShot(100,dismiss_error)
    with patch('viewers.document.QMessageBox',QuietMessageBox):
        png.open_path(invalid)
        for _ in range(200):
            QTest.qWait(10)
            if not png.pending_loads: break
    assert observed and 'CLAP-RENDER-001' in observed[0], 'Error disappeared before user could read it'
print('Native BLEND integration OK: no subprocess, RGBA Solid, rotation, async open, UI cancellation, idempotent cleanup')
