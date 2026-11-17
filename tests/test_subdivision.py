from pathlib import Path
import math,tempfile,unittest
from blend_fixture import blend_fixture
from viewers.visual.contracts import PolygonMesh,SubdivisionSettings,LoadContext,AssetFailure
from viewers.visual.subdivision import SubdivisionModifier
from viewers.visual.bootstrap import open_asset,build_registry

def cube():
    return PolygonMesh(((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)),((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)),(0,1,0,1,0,1))

class SubdivisionTests(unittest.TestCase):
    def test_catmull_clark_known_cube_and_materials(self):
        result=SubdivisionModifier().apply(cube(),SubdivisionSettings(1),LoadContext())
        self.assertEqual(len(result.mesh.positions),26); self.assertEqual(len(result.mesh.faces),24)
        for coordinate in result.mesh.positions[0]: self.assertAlmostEqual(coordinate,-5/9)
        self.assertEqual(result.mesh.materials.count(0),12); self.assertEqual(result.mesh.materials.count(1),12)
        self.assertTrue(all(abs(sum(x*x for x in n)-1)<1e-6 for n in result.mesh.normals))
    def test_simple_and_boundary_rules(self):
        result=SubdivisionModifier().apply(cube(),SubdivisionSettings(1,'simple'),LoadContext())
        self.assertEqual(result.mesh.positions[:8],cube().positions)
        quad=PolygonMesh(((0,0,0),(1,0,0),(1,1,0),(0,1,0)),((0,1,2,3),),(0,))
        result=SubdivisionModifier().apply(quad,SubdivisionSettings(1),LoadContext())
        self.assertEqual(result.mesh.positions[0],(.125,.125,0))
        result=SubdivisionModifier().apply(quad,SubdivisionSettings(1,preserve_boundary_corners=True),LoadContext())
        self.assertEqual(result.mesh.positions[0],(0,0,0))
    def test_budget_cancel_and_nonmanifold(self):
        result=SubdivisionModifier(48).apply(cube(),SubdivisionSettings(3),LoadContext())
        self.assertEqual(result.levels,1); self.assertTrue(result.notices)
        context=LoadContext(); context.cancel.set()
        with self.assertRaises(AssetFailure): SubdivisionModifier().apply(cube(),SubdivisionSettings(1),context)
        bad=PolygonMesh(((0,0,0),(1,0,0),(0,1,0),(0,-1,0),(0,0,1)),((0,1,2),(1,0,3),(0,1,4)),(0,0,0))
        with self.assertRaises(AssetFailure): SubdivisionModifier().apply(bad,SubdivisionSettings(1),LoadContext())
    def test_saved_modifier_viewport_and_materials(self):
        root=Path(__file__).resolve().parents[1]/'.test-tmp'; root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            path=Path(temp)/'subdiv.blend'
            blend_fixture(path,True,material_slots=True,subdivision=2)
            asset=open_asset(path)
            self.assertEqual(asset.info['triangles'],384)
            self.assertEqual(asset.data.material_ids.count(0),192)
            self.assertTrue(all(s['applied']==2 for s in asset.info['subdivision']))
            blend_fixture(path,True,subdivision=2,viewport=False)
            self.assertEqual(open_asset(path).info['triangles'],24)
    def test_modifier_keys_do_not_become_file_associations(self):
        registry=build_registry()
        self.assertNotIn('subdivision',registry.extensions())
        self.assertEqual(registry.operation('visual.mesh-modifier','subdivision').module_id,'clap.visual.modifier.subdivision')

if __name__=='__main__': unittest.main()
