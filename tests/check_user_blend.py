"""Explicit local acceptance of a user-selected model; never copies the asset."""
from pathlib import Path
import sys,hashlib,json,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from viewers.visual.bootstrap import open_asset,create_presentation

app=QApplication([])
path=Path(sys.argv[1]); before=hashlib.sha256(path.read_bytes()).hexdigest()
start=time.perf_counter(); asset=open_asset(path); image,renderer=create_presentation(asset)
try:
    rotated=renderer.render(image.size(),30,15,1)
    assert rotated.pixelColor(0,0).alpha()==0
    assert any(rotated.pixelColor(x,y).alpha()==255 for x in range(0,rotated.width(),8) for y in range(0,rotated.height(),8))
    out=Path(__file__).resolve().parents[1]/'.test-tmp'; out.mkdir(exist_ok=True)
    rotated.save(str(out/'user-model-solid.png'))
finally: renderer.close()
assert hashlib.sha256(path.read_bytes()).hexdigest()==before
print(json.dumps({'info':asset.info,'elapsed_seconds':round(time.perf_counter()-start,3),'source_unchanged':True,'rgba_render':'passed'},ensure_ascii=False))
