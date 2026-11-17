import unittest
from viewers.visual.contracts import MaterialData,MaterialOp,AssetFailure
from viewers.visual.renderers.material_shader import fragment_shader

def material(nodes): return MaterialData('test',tuple(nodes),0,0,0)

class MaterialGraphTests(unittest.TestCase):
    def test_saved_material_slots_and_face_indices(self):
        from pathlib import Path
        import tempfile
        from blend_fixture import blend_fixture
        from viewers.visual.bootstrap import open_asset
        root=Path(__file__).resolve().parents[1]/'.test-tmp'; root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            path=Path(tmp)/'materials.blend'; blend_fixture(path,material_slots=True)
            asset=open_asset(path)
            self.assertIn('view.materials',asset.capabilities)
            self.assertEqual(len(asset.data.materials),2)
            self.assertEqual(asset.data.material_ids.count(0),12)
            self.assertEqual(asset.data.material_ids.count(1),12)
    def test_unknown_operations_and_invalid_graphs_rejected(self):
        for graph in [material([MaterialOp('script')]),material([MaterialOp('luminance',(0,))]),material([MaterialOp('constant',values=(float('nan'),)*4)])]:
            with self.assertRaises((AssetFailure,ValueError)): fragment_shader(graph)
    def test_graph_budget(self):
        with self.assertRaises(AssetFailure): fragment_shader(material([MaterialOp('constant',values=(.5,)*4)]*257))
    def test_shader_contains_no_material_name_as_code(self):
        graph=MaterialData('"; malicious_name();', (MaterialOp('constant',values=(.1,.2,.3,1)),),0,0,0)
        source=fragment_shader(graph)
        self.assertNotIn(graph.name,source)
        self.assertIn('vec4 n0=',source)

if __name__=='__main__': unittest.main()
