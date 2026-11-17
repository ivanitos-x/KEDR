import json
import struct
from pathlib import Path
import tempfile
import unittest
from viewers.png import load_glb
from viewers.core import ViewerError

def fixture(path,change=None):
    binary=struct.pack('<9f',-1,-1,0,1,-1,0,0,1,0)
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
         'bufferViews':[{'buffer':0,'byteLength':len(binary)}],
         'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'}],
         'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}],
         'nodes':[{'mesh':0},{'mesh':0,'translation':[3,0,0]}],
         'scenes':[{'nodes':[0,1]}],'scene':0}
    if change: change(doc)
    raw=json.dumps(doc).encode(); raw+=b' '*((-len(raw))%4)
    payload=struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(binary),0x004e4942)+binary
    path.write_bytes(struct.pack('<4sII',b'glTF',2,len(payload)+12)+payload)

class GlbTests(unittest.TestCase):
    def test_material_factors_and_primitive_assignment(self):
        def change(doc):
            doc['materials']=[{'pbrMetallicRoughness':{'baseColorFactor':[.8,.1,.05,1],'roughnessFactor':.25,'metallicFactor':.9},'normalTexture':{'index':0}}]
            doc['meshes'][0]['primitives'][0]['material']=0
        fixture(self.path,change)
        data=load_glb(self.path,include_scene=True)
        self.assertEqual(data.material_ids,(0,0))
        self.assertEqual(data.materials[0].nodes[0].values,(.8,.1,.05,1))
        self.assertEqual(data.materials[0].nodes[1].values[0],.25)
        self.assertTrue(data.materials[0].notices)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.test-tmp')
        self.path=Path(self.tmp.name)/'модель с пробелами.glb'
    def tearDown(self): self.tmp.cleanup()
    def test_multi_object_and_normalization(self):
        fixture(self.path); before=self.path.read_bytes(); v,info=load_glb(self.path)
        self.assertEqual(info['objects'],2); self.assertEqual(info['triangles'],2)
        self.assertLess(v[0],v[18]); self.assertLessEqual(max(abs(x) for x in v),1)
        self.assertEqual(self.path.read_bytes(),before)
    def test_bad_header_and_bounds(self):
        self.path.write_bytes(b'bad')
        with self.assertRaises(ViewerError): load_glb(self.path)
        fixture(self.path,lambda d:d['accessors'][0].update(byteOffset=900))
        with self.assertRaises(ViewerError): load_glb(self.path)
    def test_external_buffer_and_cycle_rejected(self):
        for change in [lambda d:d['buffers'][0].update(uri='https://example.com/model.bin'),lambda d:d['nodes'][0].update(children=[0]),lambda d:d.update(extensionsRequired=['KHR_draco_mesh_compression'])]:
            fixture(self.path,change)
            with self.assertRaises(ViewerError): load_glb(self.path)
    def test_matrix_column_major(self):
        fixture(self.path,lambda d:d['nodes'][1].update(matrix=[1,0,0,0,0,1,0,0,0,0,1,0,3,0,0,1]))
        v,_=load_glb(self.path); self.assertLess(v[0],v[18])

if __name__=='__main__': unittest.main()
