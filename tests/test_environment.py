from pathlib import Path
import tempfile,unittest
from viewers.visual.environment import load_hdr
from viewers.visual.contracts import AssetFailure

class HdrTests(unittest.TestCase):
    def test_cancel_preserves_cancelled_status(self):
        from viewers.visual.contracts import LoadContext
        context=LoadContext(); context.cancel.set()
        with self.assertRaises(AssetFailure) as caught: load_hdr(Path('unused.hdr'),context)
        self.assertEqual(caught.exception.status,'cancelled')
    def test_renderer_failure_keeps_working_mode(self):
        from viewers.visual.contracts import Descriptor,DisplayMode,SceneData
        from viewers.visual.registry import Registry
        from viewers.visual.presentation import RendererSession
        class Working:
            closed=False
            def render(self,*args): return 'frame'
            def close(self): self.closed=True
        class Broken(Working):
            def set_display_mode(self,mode): pass
            def render(self,*args): raise RuntimeError('GPU failed')
        good=Working(); bad=Broken(); registry=Registry()
        for key,backend in [('solid',good),('pbr',bad)]:
            registry.register(Descriptor(key,'1','visual.scene-renderer','1.0',frozenset(),(key,),(),{},frozenset(),lambda _,b=backend:b,modes=(DisplayMode(key,key),)))
        registry.validate(); session=RendererSession(SceneData(b'',{}),registry); session.render('size',0,0,1)
        with self.assertRaisesRegex(RuntimeError,'GPU failed'): session.set_display_mode('pbr')
        self.assertEqual(session.mode,'solid'); self.assertFalse(good.closed); self.assertTrue(bad.closed)
        session.close(); self.assertTrue(good.closed)
    def test_raw_and_rle_hdr(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.test-tmp') as tmp:
            path=Path(tmp)/'light.hdr'
            header=b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n'
            path.write_bytes(header+b'-Y 1 +X 1\n'+bytes([100,150,200,130]))
            self.assertEqual(load_hdr(path).rgbe,bytes([100,150,200,130]))
            path.write_bytes(header+b'-Y 1 +X 8\n'+bytes([2,2,0,8,136,100,136,150,136,200,136,130]))
            self.assertEqual(load_hdr(path).rgbe,bytes([100,150,200,130])*8)
    def test_corrupt_and_oversized_hdr(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.test-tmp') as tmp:
            path=Path(tmp)/'bad.hdr'
            for data in [b'not HDR',b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 99999\n',b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 8\n'+bytes([2,2,0,8,0])]:
                path.write_bytes(data)
                with self.assertRaises(AssetFailure): load_hdr(path)
