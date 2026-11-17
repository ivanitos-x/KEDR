"""Explicit user-file acceptance; no Blender, writes only a rendered test artifact."""
from pathlib import Path
import sys,hashlib,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from viewers.visual.bootstrap import open_asset,create_presentation
app=QApplication([]); path=Path(sys.argv[1]); before=hashlib.sha256(path.read_bytes()).hexdigest(); start=time.perf_counter()
with patch('subprocess.Popen',side_effect=AssertionError('Blender is forbidden')):
    asset=open_asset(path); solid,session=create_presentation(asset); session.set_display_mode('pbr')
    try:
        frame=session.render(solid.size(),30,15,1)
        assert frame.pixelColor(0,0).alpha()==0 and frame!=solid
        assert any(frame.pixelColor(x,y).alpha()==255 for x in range(0,frame.width(),8) for y in range(0,frame.height(),8))
        output=Path(__file__).resolve().parents[1]/'.test-tmp'; frame.save(str(output/'user-pbr.png'))
        session.set_display_mode('materials'); preview=session.render(solid.size(),30,15,1); assert preview!=frame
        session.set_display_mode('pbr'); assert frame==session.render(solid.size(),30,15,1)
    finally:session.close();session.close()
assert hashlib.sha256(path.read_bytes()).hexdigest()==before
print('User PBR, subdivision, procedural material, alpha, modes and input hash OK:',asset.info,'seconds',round(time.perf_counter()-start,3))
