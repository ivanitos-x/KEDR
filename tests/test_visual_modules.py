import dataclasses
import gzip
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from blend_fixture import blend_fixture
from viewers.visual.bootstrap import build_registry,open_asset,file_filter
from viewers.visual.contracts import Descriptor,Asset,AssetFailure,RasterData,LoadContext
from viewers.visual.application import OpenAsset
from viewers.visual.formats.blend import BlendLoader
from viewers.visual.registry import Registry
from viewers.associations import applications
from viewers.visual.geometry import triangulate
from viewers.visual.formats.blend_dna import BlendFile

class NativeBlendTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.test-tmp'; root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root); self.path=Path(self.temp.name)/'модель тест.blend'
    def tearDown(self): self.temp.cleanup()
    def test_old_and_modern_meshes_no_blender(self):
        for modern,attributes in [(False,False),(True,False),(True,True)]:
            raw=blend_fixture(self.path,modern,attributes)
            with patch('subprocess.Popen',side_effect=AssertionError('No Blender / subprocess allowed')):
                asset=open_asset(self.path)
            self.assertEqual(asset.info['triangles'],24)
            self.assertEqual(asset.info['objects'],2)
            self.assertEqual(asset.info['vertices'],16)
            floats=struct.unpack('<'+'f'*(len(asset.data.vertices)//4),asset.data.vertices)
            self.assertLess(sum(floats[i] for i in range(0,36*6,6)),sum(floats[i] for i in range(36*6,72*6,6)))
            self.assertEqual(self.path.read_bytes(),raw)
    def test_gzip_and_zstandard(self):
        import zstandard
        raw=blend_fixture(self.path,True,True)
        for compressed in [gzip.compress(raw),zstandard.ZstdCompressor().compress(raw)]:
            self.path.write_bytes(compressed)
            self.assertEqual(open_asset(self.path).info['triangles'],24)
    def test_parent_transform_and_nonuniform_scale(self):
        blend_fixture(self.path,True,True,parented=True)
        asset=open_asset(self.path)
        values=struct.unpack('<'+'f'*(len(asset.data.vertices)//4),asset.data.vertices)
        first=[values[i+2] for i in range(0,216,6)]; second=[values[i+2] for i in range(216,432,6)]
        self.assertGreater(sum(first)/36,sum(second)/36+.5)
    def test_duplicate_corners_and_unrelated_addresses(self):
        points=[(0,0,0),(1,0,0),(1,0,0),(1,1,0),(0,1,0)]
        triangles=triangulate(points,LoadContext())
        self.assertEqual(len(triangles),2)
        raw=blend_fixture(self.path)
        # Reused non-geometry DATA identity is legal; requested conflicting
        # geometry identity still fails instead of silently choosing a block.
        unrelated=struct.pack('<4sIQII',b'DATA',4,0x14000,0,1)+b'AAAA'
        unrelated+=struct.pack('<4sIQII',b'DATA',4,0x14000,0,1)+b'BBBB'
        self.path.write_bytes(raw[:-24]+unrelated+raw[-24:])
        self.assertEqual(open_asset(self.path).info['triangles'],24)
        conflicting=struct.pack('<4sIQII',b'DATA',12,0x1000,0,1)+bytes(12)
        self.path.write_bytes(raw[:-24]+conflicting+raw[-24:])
        with self.assertRaises(AssetFailure): open_asset(self.path)
    def test_reject_corrupt_and_linked(self):
        raw=blend_fixture(self.path)
        for data in [raw[:80],b'BLENDER-v280'+b'\0'*30]:
            self.path.write_bytes(data)
            with self.assertRaises(AssetFailure): open_asset(self.path)
        blend_fixture(self.path,library=True)
        with self.assertRaises(AssetFailure) as error: open_asset(self.path)
        self.assertEqual(error.exception.status,'unsupported')
    def test_cancel_timeout_and_expansion_limit(self):
        blend_fixture(self.path)
        ctx=LoadContext(); ctx.cancel.set()
        with self.assertRaises(AssetFailure) as error: open_asset(self.path,ctx)
        self.assertEqual(error.exception.status,'cancelled')
        with self.assertRaises(AssetFailure): open_asset(self.path,LoadContext(timeout=0))
        self.path.write_bytes(gzip.compress(b'A'*10000))
        with patch('viewers.visual.formats.blend_dna.MAX_FILE',1024),self.assertRaises(AssetFailure):
            BlendLoader().load(self.path,LoadContext())

class FakeLoader:
    def probe(self,header): return header.startswith(b'FAKE')
    def load(self,path,context): return Asset(RasterData(bytes([255,0,0,255])*4,2,2,False),frozenset({'view.move','view.zoom'}),{'width':2,'height':2,'alpha':False})

def descriptor(**changes):
    d=Descriptor('test.format','1.0','visual.asset-loader','1.0',frozenset({'raster.decode'}),('.fake',),(),{'input_bytes':64},frozenset({'file.read.selected'}),FakeLoader)
    return dataclasses.replace(d,**changes)

class RegistryTests(unittest.TestCase):
    def test_duplicate_api_and_permissions(self):
        r=Registry(); r.register(descriptor())
        for d in [descriptor(),descriptor(module_id='api',api_version='2.0'),descriptor(module_id='permissions',permissions=frozenset({'network'}))]:
            with self.assertRaises(ValueError): r.register(d)
    def test_missing_and_cyclic_dependencies(self):
        r=Registry(); r.register(descriptor(requires=('missing',)))
        with self.assertRaises(ValueError): r.validate()
        r=Registry(); r.register(descriptor(requires=('second',))); r.register(descriptor(module_id='second',requires=('test.format',)))
        with self.assertRaises(ValueError): r.validate()
    def test_unavailable_and_ambiguous(self):
        r=Registry(); r.register(descriptor(unavailable='optional library missing')); r.validate()
        self.assertEqual(r.extensions(),())
        with self.assertRaises(AssetFailure) as error: r.resolve('.fake',b'FAKE')
        self.assertEqual(error.exception.status,'unavailable')
        r=Registry(); r.register(descriptor()); r.register(descriptor(module_id='other'))
        with self.assertRaises(AssetFailure): r.resolve('.fake',b'FAKE')
    def test_new_format_needs_no_ui_or_core_change(self):
        from PySide6.QtWidgets import QApplication
        from viewers.png import PngWindow
        app=QApplication.instance() or QApplication([])
        r=build_registry(); r.register(descriptor()); r.validate()
        root=Path(__file__).resolve().parents[1]/'.test-tmp'; root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            path=Path(temp)/'new.fake'; path.write_bytes(b'FAKE')
            asset=OpenAsset(r)(path)
            with patch('viewers.visual.bootstrap.build_registry',return_value=r):
                self.assertIn('*.fake',file_filter())
            self.assertNotIn('.fake',applications(r)['CLAP.PNG'][1])
            self.assertEqual(set(applications(r)['CLAP.PNG'][1]), {'.blend','.glb','.kvx','.md2','.md3'})
            win=PngWindow(path,asset); self.assertFalse(win.is_model); self.assertEqual(win.image.width(),2); win.close()
    def test_signature_mismatch_does_not_fallback(self):
        r=Registry(); r.register(descriptor())
        with self.assertRaises(AssetFailure) as error: r.resolve('.fake',b'not fake')
        self.assertEqual(error.exception.status,'invalid_input')
    def test_cleanup_failure_preserves_render_error(self):
        from PySide6.QtWidgets import QApplication
        from viewers.visual.bootstrap import create_presentation
        from viewers.visual.contracts import SceneData
        app=QApplication.instance() or QApplication([])
        class BrokenRenderer:
            closed=False
            def render(self,*args): raise RuntimeError('original render failure')
            def close(self): self.closed=True; raise RuntimeError('cleanup failure')
        renderer=BrokenRenderer()
        registry=Registry(); registry.register(descriptor(module_id='clap.visual.renderer.solid',contract_id='visual.scene-renderer',accepts=('solid',),factory=lambda _:renderer))
        with patch('viewers.visual.bootstrap.build_registry',return_value=registry),self.assertRaisesRegex(RuntimeError,'original render failure'):
            create_presentation(Asset(SceneData(b'',{}),frozenset(),{}))
        self.assertTrue(renderer.closed)

if __name__=='__main__': unittest.main()
