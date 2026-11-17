import struct
from pathlib import Path
import tempfile
import unittest

from viewers.core import ViewerError
from viewers.visual.contracts import LoadContext
from viewers.visual.formats.kvx import KvxLoader, read_kvx


def fixture(path, visibility=0x3F, color=7, include_mip=False, run_length=1, colors=None):
    xs = ys = 1
    zs = run_length
    x_table_size = (xs + 1) * 4
    y_table_size = xs * (ys + 1) * 2
    table_size = x_table_size + y_table_size
    color_data = bytes(colors) if colors is not None else bytes((color,)) * run_length
    if len(color_data) != run_length:
        raise ValueError('Color count must match the slab length')
    slab = bytes((0, run_length, visibility)) + color_data
    x_offsets = struct.pack('<2I', table_size, table_size + len(slab))
    y_offsets = struct.pack('<2H', 0, len(slab))
    header = struct.pack('<6i', xs, ys, zs, 0, 0, 0)
    mip = struct.pack('<I', len(header) + len(x_offsets) + len(y_offsets) + len(slab))
    mip += header + x_offsets + y_offsets + slab
    if include_mip:
        second_header = struct.pack('<6i', 1, 1, 1, 0, 0, 0)
        second_slab = bytes((0, 1, 0x3F, color))
        second = struct.pack('<I', len(second_header) + 12 + len(second_slab))
        second += second_header + struct.pack('<2I', 12, 12 + len(second_slab))
        second += struct.pack('<2H', 0, len(second_slab)) + second_slab
        mip += second
    palette = bytes((0, 0, 0) * color + (63, 0, 0) + (0, 0, 0) * (255 - color))
    path.write_bytes(mip + palette)


class KvxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'voxel.kvx'

    def tearDown(self):
        self.directory.cleanup()

    def test_voxel_faces_keep_palette_indices_and_default_to_solid(self):
        fixture(self.path, color=7)
        scene = read_kvx(self.path)
        self.assertEqual(scene.info['format'], 'KVX')
        self.assertEqual(scene.info['voxels'], 1)
        self.assertEqual(scene.info['triangles'], 12)
        self.assertEqual(len(scene.materials), 1)
        self.assertEqual(scene.materials[0].texture.width, 256)
        self.assertEqual(scene.materials[0].texture.height, 1)
        self.assertEqual(scene.material_ids, (0,) * 12)
        self.assertEqual(len(scene.vertices), 12 * 3 * 6 * 4)
        self.assertEqual(len(scene.coordinates), 12 * 3 * 3 * 4)
        asset = KvxLoader().load(self.path, LoadContext())
        self.assertEqual(asset.preferred_mode, 'solid')
        self.assertIn('view.materials', asset.capabilities)
        self.assertIn('view.palette', asset.capabilities)

    def test_visibility_masks_and_mip_levels(self):
        fixture(self.path, visibility=1 << 5, include_mip=True)
        scene = read_kvx(self.path)
        self.assertEqual(scene.info['triangles'], 2)
        self.assertEqual(scene.material_ids, (0, 0))

    def test_vertical_slab_has_one_prism_boundary(self):
        fixture(self.path, run_length=3)
        scene = read_kvx(self.path)
        self.assertEqual(scene.info['voxels'], 3)
        self.assertEqual(scene.info['triangles'], 12)

    def test_side_faces_split_only_when_palette_index_changes(self):
        fixture(self.path, visibility=1, run_length=3, colors=(7, 7, 8))
        scene = read_kvx(self.path)
        self.assertEqual(scene.info['triangles'], 4)
        self.assertEqual(scene.material_ids, (0, 0, 0, 0))
        values = struct.unpack('<' + 'f' * (len(scene.coordinates) // 4), scene.coordinates)
        sampled_indices = {
            round(values[index] * 256 - 0.5)
            for index in range(0, len(values), 3)
        }
        self.assertEqual(sampled_indices, {7, 8})

    def test_rejects_bad_tables_and_detects_by_structure(self):
        fixture(self.path)
        data = bytearray(self.path.read_bytes())
        data[32:36] = struct.pack('<I', 0)
        self.path.write_bytes(data)
        with self.assertRaises(ViewerError):
            read_kvx(self.path)
        self.assertTrue(KvxLoader().probe(struct.pack('<4i', 40, 1, 1, 1)))
        self.assertFalse(KvxLoader().probe(b'bad'))


if __name__ == '__main__':
    unittest.main()
