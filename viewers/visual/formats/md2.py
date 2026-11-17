"""Bounded Quake II MD2 loader for the first animation frame."""
from array import array
import math
from pathlib import Path
import struct

from ...core import ViewerError
from ..contracts import Asset, AssetFailure

MD2_IDENT = b'IDP2'
MD2_VERSION = 8
HEADER_SIZE = 68
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SKINS = 32
MAX_VERTICES = 2048
MAX_TRIANGLES = 4096
MAX_FRAMES = 512
MAX_SKIN_SIZE = 4096


def _inside(offset, size, end):
    return offset >= HEADER_SIZE and size >= 0 and offset + size <= end


def _text(raw):
    return raw.split(b'\0', 1)[0].decode('utf-8', errors='replace')


def load_md2(path, context=None):
    path = Path(path).resolve()
    try:
        if context:
            context.check()
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise OverflowError('Лимит MD2 — 64 МиБ')
        if len(raw) < HEADER_SIZE:
            raise ValueError('Оборван заголовок MD2')
        header = struct.unpack_from('<17i', raw)
        (ident, version, skin_width, skin_height, frame_size, skin_count,
         vertex_count, st_count, triangle_count, command_count, frame_count,
         skin_offset, st_offset, triangle_offset, frame_offset, command_offset,
         end_offset) = header
        if ident != struct.unpack('<i', MD2_IDENT)[0] or version != MD2_VERSION:
            raise ValueError('Ожидается MD2 версии 8')
        if not (1 <= skin_width <= MAX_SKIN_SIZE and 1 <= skin_height <= MAX_SKIN_SIZE):
            raise ValueError('Размер текстуры MD2 выходит за допустимые пределы')
        if (not 0 <= skin_count <= MAX_SKINS or not 1 <= vertex_count <= MAX_VERTICES
                or not 1 <= st_count <= MAX_VERTICES or not 1 <= triangle_count <= MAX_TRIANGLES
                or not 1 <= frame_count <= MAX_FRAMES or command_count < 0):
            raise OverflowError('Счётчики MD2 выходят за допустимые пределы')
        if end_offset != len(raw) or frame_size != 40 + vertex_count * 4:
            raise ValueError('Некорректный размер файла или кадра MD2')
        ranges = (
            (skin_offset, skin_count * 64),
            (st_offset, st_count * 4),
            (triangle_offset, triangle_count * 12),
            (frame_offset, frame_count * frame_size),
            (command_offset, command_count * 4),
        )
        for offset, size in ranges:
            if size == 0 and offset in (0, end_offset):
                continue
            if not _inside(offset, size, end_offset):
                raise ValueError('Таблица MD2 выходит за границы файла')
        if context:
            context.check()

        skin_names = tuple(
            _text(raw[skin_offset + i * 64:skin_offset + (i + 1) * 64])
            for i in range(skin_count)
        )
        texcoords = [
            struct.unpack_from('<2h', raw, st_offset + i * 4)
            for i in range(st_count)
        ]
        triangles = []
        for index in range(triangle_count):
            if context and index % 512 == 0:
                context.check()
            values = struct.unpack_from('<6H', raw, triangle_offset + index * 12)
            xyz, st = values[:3], values[3:]
            if max(xyz) >= vertex_count or max(st) >= st_count:
                raise ValueError('Индекс вершины или UV в MD2 вне диапазона')
            triangles.append((xyz, st))

        frame = frame_offset
        scale = struct.unpack_from('<3f', raw, frame)
        translate = struct.unpack_from('<3f', raw, frame + 12)
        if any(not math.isfinite(value) or abs(value) > 1e6 for value in (*scale, *translate)):
            raise ValueError('Некорректное преобразование вершин MD2')
        positions = []
        for index in range(vertex_count):
            if context and index % 512 == 0:
                context.check()
            x, y, z, _normal_index = struct.unpack_from('<4B', raw, frame + 40 + index * 4)
            compressed = (x, y, z)
            point = tuple(compressed[axis] * scale[axis] + translate[axis]
                          for axis in range(3))
            # Quake II models use Z-up. The viewer uses Y-up.
            positions.append((point[0], point[2], -point[1]))

        low = tuple(min(point[axis] for point in positions) for axis in range(3))
        high = tuple(max(point[axis] for point in positions) for axis in range(3))
        center = tuple((a + b) / 2 for a, b in zip(low, high))
        radius = math.sqrt(sum((b - a) ** 2 for a, b in zip(low, high))) / 2
        if radius <= 1e-12:
            raise ValueError('Нулевой размер MD2-модели')

        vertices = array('f')
        coordinates = array('f')
        for xyz, st in triangles:
            p0, p1, p2 = (positions[i] for i in xyz)
            edge_a = tuple(p1[i] - p0[i] for i in range(3))
            edge_b = tuple(p2[i] - p0[i] for i in range(3))
            normal = (edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
                      edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
                      edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0])
            normal_length = math.sqrt(sum(value * value for value in normal))
            if normal_length <= 1e-12:
                continue
            normal = tuple(value / normal_length for value in normal)
            for vertex_index, st_index in zip(xyz, st):
                point = positions[vertex_index]
                normalized = tuple((point[i] - center[i]) / radius for i in range(3))
                vertices.extend((*normalized, *normal))
                s, t = texcoords[st_index]
                coordinates.extend((s / skin_width, t / skin_height, 0.0))
        if not vertices:
            raise ValueError('В MD2 нет треугольников с ненулевой площадью')
        info = {
            'format': 'MD2',
            'frames': frame_count,
            'frame': 0,
            'surfaces': 1,
            'objects': 1,
            'bytes': len(raw),
            'vertices': vertex_count,
            'triangles': len(vertices) // 18,
            'skin_size': (skin_width, skin_height),
            'skin_names': skin_names,
        }
        notices = (f'Показан первый кадр из {frame_count}.',) if frame_count > 1 else ()
        from .model_texture import textured_model
        return textured_model(path, context, info, vertices.tobytes(),
                              coordinates.tobytes(), notices,
                              skin_names=skin_names)
    except (MemoryError, OverflowError) as exc:
        raise ViewerError('CLAP-RENDER-004', exc, file=path) from exc
    except Exception as exc:
        if isinstance(exc, (AssetFailure, ViewerError)):
            raise
        raise ViewerError('CLAP-RENDER-001', exc, file=path) from exc


class Md2Loader:
    def probe(self, header):
        return header.startswith(MD2_IDENT)

    def load(self, path, context):
        return load_md2(path, context)
