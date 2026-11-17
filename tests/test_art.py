import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from viewers.core import ViewerError
from viewers.visual.contracts import LoadContext
from viewers.visual.formats.art import ArtLoader, load_art, load_art_asset


def write_art(path, first_id, tiles, declared_tiles=None):
    """Each tile is (width, height, picanm, pixels-in-column-order)."""
    last_id = first_id + len(tiles) - 1
    declared = declared_tiles if declared_tiles is not None else len(tiles)
    raw = bytearray(struct.pack('<4i', 1, declared, first_id, last_id))
    raw.extend(struct.pack(f'<{len(tiles)}H', *(tile[0] for tile in tiles)))
    raw.extend(struct.pack(f'<{len(tiles)}H', *(tile[1] for tile in tiles)))
    raw.extend(struct.pack(f'<{len(tiles)}I', *(tile[2] for tile in tiles)))
    for _, _, _, pixels in tiles:
        raw.extend(pixels)
    path.write_bytes(raw)


def tile(width, height, picanm=0, pixels=None):
    return width, height, picanm, bytes(pixels if pixels is not None
                                         else range(width * height))


def picanm(frames, kind, speed=0):
    return frames | (kind << 6) | (speed << 24)


def write_grp(path, entries):
    records = [struct.pack('<12sI', name.encode('ascii'), len(content))
               for name, content in entries]
    path.write_bytes(struct.pack('<12sI', b'KenSilverman', len(entries))
                     + b''.join(records) + b''.join(content for _, content in entries))


class ArtTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / 'TILES000.ART'

    def tearDown(self):
        self.directory.cleanup()

    def test_header_pixel_transpose_and_palette(self):
        write_art(self.path, 0, [tile(2, 3, pixels=(1, 2, 3, 4, 5, 6))],
                  declared_tiles=256)
        palette = bytes((index % 64 for index in range(768)))
        (self.root / 'PALETTE.DAT').write_bytes(palette + b'extra')
        data = load_art(self.path)
        self.assertEqual(data.palette, palette)
        self.assertEqual(tuple(data.tiles), (0,))
        self.assertEqual(data.tiles[0].pixels, bytes((1, 4, 2, 5, 3, 6)))
        self.assertEqual((data.tiles[0].width, data.tiles[0].height), (2, 3))
        self.assertTrue(ArtLoader().probe(self.path.read_bytes()[:16]))

    def test_build_animation_directions_speed_and_adjacent_frames(self):
        write_art(self.path, 100, [
            tile(1, 1, picanm(2, 2, 1), (11,)),
            tile(1, 1, picanm(2, 1, 0), (12,)),
        ], declared_tiles=512)
        second = self.root / 'TILES001.ART'
        write_art(second, 102, [tile(1, 1, pixels=(13,)), tile(1, 1, pixels=(14,))],
                  declared_tiles=768)
        data = load_art(self.path)
        self.assertEqual(set(data.tiles), {100, 101})
        self.assertEqual(data.frame(100, 0), 100)
        self.assertEqual(data.frame(100, 1), 100)
        self.assertEqual(data.frame(100, 2), 101)
        self.assertIn(102, data.frames)
        self.assertEqual(data.frame(100, 4), 102)
        self.assertEqual(data.frames[102].pixels, b'\x0d')
        self.assertEqual(data.frame(100, 6), 100)
        self.assertEqual(data.frame(101, 1), 102)
        self.assertEqual(data.frame(101, 2), 103)
        backward = picanm(2, 3)
        write_art(self.path, 100, [tile(1, 1, pixels=(20,)),
                                   tile(1, 1, pixels=(21,)),
                                   tile(1, 1, backward, (22,))])
        data = load_art(self.path)
        self.assertEqual([data.frame(102, ticks) for ticks in (0, 1, 2, 3)],
                         [102, 101, 100, 102])

    def test_ping_pong_wrap_missing_frame_and_explicit_palette(self):
        write_art(self.path, 5, [
            tile(1, 1, picanm(2, 1), (1,)),
            tile(1, 1, pixels=(2,)),
            tile(1, 1, pixels=(3,)),
        ])
        data = load_art(self.path)
        self.assertEqual([data.frame(5, tick) for tick in range(6)],
                         [5, 6, 7, 6, 5, 6])
        write_art(self.path, 5, [tile(1, 1, picanm(2, 2), (1,))])
        self.assertIsNone(load_art(self.path).frame(5, 2))
        palette = self.root / 'custom.dat'
        palette.write_bytes(bytes((7, 8, 9)) * 256)
        context = LoadContext(palette_path=palette)
        self.assertEqual(load_art(self.path, context).palette, palette.read_bytes())

    def test_rejects_truncated_or_inconsistent_art(self):
        self.path.write_bytes(b'\x01\x00')
        with self.assertRaises(ViewerError):
            load_art(self.path)
        write_art(self.path, 0, [tile(2, 2)])
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaises(ViewerError):
            load_art(self.path)
        write_art(self.path, 0, [tile(1, 1)])
        self.path.write_bytes(struct.pack('<4i', 2, 1, 0, 0) + self.path.read_bytes()[16:])
        self.assertFalse(ArtLoader().probe(self.path.read_bytes()[:16]))
        with self.assertRaises(ViewerError):
            load_art(self.path)

    def test_grp_uses_physical_order_for_selection_and_tile_order_for_navigation(self):
        archive = self.root / 'with spaces.grp'
        write_art(self.path, 11, [tile(1, 1, pixels=(31,))])
        later = self.path.read_bytes()
        write_art(self.path, 10, [tile(1, 1, picanm(1, 2), (21,))])
        earlier = self.path.read_bytes()
        palette = bytes((4, 5, 6)) * 256
        write_grp(archive, [('SAME.ART', later), ('PALETTE.DAT', palette),
                            ('SAME.ART', earlier)])
        data = load_art_asset(archive, entry_index=2).data
        self.assertEqual([(item.name, item.entry_index) for item in data.entries],
                         [('SAME.ART', 2), ('SAME.ART', 0)])
        self.assertEqual(data.entries[data.position].path, archive.resolve())
        self.assertEqual(data.palette, palette)
        self.assertIn('PALETTE.DAT', data.palette_source)
        self.assertEqual(data.frame(10, 1), 11)
        self.assertEqual(data.frames[11].pixels, bytes((31,)))
        self.assertEqual(load_art(archive, entry_index=0).position, 1)
        for index in (-1, 1, 3):
            with self.assertRaises(ViewerError):
                load_art(archive, entry_index=index)
        archive.write_bytes(archive.read_bytes()[:-1])
        with self.assertRaises(ViewerError):
            load_art(archive, entry_index=0)

    def test_palette_fallback_and_loose_catalog_order(self):
        earlier = self.root / 'ZZZ.ART'
        write_art(self.path, 11, [tile(1, 1)])
        write_art(earlier, 10, [tile(1, 1)])
        adjacent = self.root / 'PALETTE.DAT'
        adjacent.write_bytes(b'bad')
        saved = self.root / 'saved.dat'
        saved.write_bytes(bytes(768))
        context = LoadContext()
        context.saved_palette_path = saved
        data = load_art(self.path, context)
        self.assertEqual([item.name for item in data.entries], ['ZZZ.ART', 'TILES000.ART'])
        self.assertEqual(data.position, 1)
        self.assertEqual(Path(data.palette_source), saved.resolve())
        adjacent.write_bytes(bytes([1]) * 768)
        self.assertEqual(Path(load_art(self.path, context).palette_source), adjacent.resolve())
        saved.unlink()
        adjacent.unlink()
        data = load_art(self.path, context)
        self.assertIsNone(data.palette)
        self.assertTrue(data.palette_issue)


if __name__ == '__main__':
    unittest.main()
