"""Bounded Quake III MD3 static-frame loader."""
from array import array
from pathlib import Path
import math
import struct

from ...core import ViewerError
from ..contracts import AssetFailure
from .model_texture import textured_model

MD3_IDENT = b'IDP3'
MD3_VERSION = 15
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SURFACES = 32
MAX_FRAMES = 1024
MAX_VERTICES_PER_SURFACE = 4096
MAX_TRIANGLES_PER_SURFACE = 8192


def _inside(offset, size, start, end):
    return offset >= start and size >= 0 and offset + size <= end


def _name(value):
    return value.split(b'\0', 1)[0].decode('utf-8', errors='replace')


def _load_md3(path, context=None):
    """Decode the first animation frame; MD3 animation and tags remain metadata."""
    path = Path(path).resolve()
    try:
        if context:
            context.check()
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise OverflowError('Лимит MD3 — 64 МиБ')
        if len(raw) < 108:
            raise ValueError('Оборванный заголовок MD3')
        ident, version, model_name, flags, frame_count, tag_count, surface_count, skin_count, frame_offset, tag_offset, surface_offset, end_offset = struct.unpack_from(
            '<4si64s9i', raw, 0
        )
        if ident != MD3_IDENT or version != MD3_VERSION:
            raise ValueError('Ожидается формат IDP3 версии 15')
        if not 1 <= frame_count <= MAX_FRAMES or not 1 <= surface_count <= MAX_SURFACES:
            raise OverflowError('Превышен лимит кадров или поверхностей MD3')
        if end_offset != len(raw) or not 108 <= surface_offset < end_offset:
            raise ValueError('Некорректная длина MD3 или смещение поверхностей')
        if not _inside(frame_offset, frame_count * 56, 108, end_offset):
            raise ValueError('Таблица кадров выходит за границы файла')
        if (not 0 <= tag_count <= 16 or not 0 <= skin_count <= 4096
                or not _inside(tag_offset, frame_count * tag_count * 112, 108, end_offset)):
            raise ValueError('Некорректные счётчики или смещение MD3')
        if context:
            context.check()

        positions = []
        triangles = []
        uvs = []
        surface_names = []
        surface_cursor = surface_offset
        for _ in range(surface_count):
            if not _inside(surface_cursor, 108, surface_offset, end_offset):
                raise ValueError('Оборван заголовок поверхности MD3')
            header = struct.unpack_from('<4s64s10i', raw, surface_cursor)
            surface_ident, surface_name = header[:2]
            (surface_flags, frames, shader_count, vertex_count, triangle_count,
             triangle_offset, shader_offset, uv_offset, vertex_offset, surface_end) = header[2:]
            if surface_ident != MD3_IDENT or not 1 <= frames <= frame_count:
                raise ValueError('Некорректная поверхность MD3')
            if not 0 <= shader_count <= 256 or not 0 < vertex_count <= MAX_VERTICES_PER_SURFACE or not 0 < triangle_count <= MAX_TRIANGLES_PER_SURFACE:
                raise OverflowError('Поверхность MD3 превышает лимиты геометрии')
            if surface_end < 108 or surface_cursor + surface_end > end_offset:
                raise ValueError('Некорректная длина поверхности MD3')
            local_end = surface_cursor + surface_end
            sections = (
                (triangle_offset, triangle_count * 12),
                (shader_offset, shader_count * 68),
                (uv_offset, vertex_count * 8),
                (vertex_offset, frames * vertex_count * 8),
            )
            for section_offset, section_size in sections:
                if not _inside(surface_cursor + section_offset, section_size, surface_cursor + 108, local_end):
                    raise ValueError('Данные поверхности MD3 выходят за её границы')
            base_vertex = len(positions)
            surface_vertices = []
            for index in range(vertex_count):
                if context and index % 512 == 0:
                    context.check()
                s, t = struct.unpack_from('<ff', raw, surface_cursor + uv_offset + index * 8)
                if not math.isfinite(s) or not math.isfinite(t) or abs(s) > 1e5 or abs(t) > 1e5:
                    raise ValueError('Некорректные UV координаты MD3')
                uvs.append((s, t))
                x, y, z, encoded_normal = struct.unpack_from(
                    '<3hH', raw, surface_cursor + vertex_offset + index * 8
                )
                latitude = ((encoded_normal >> 8) & 255) * (2 * math.pi / 255.0)
                longitude = (encoded_normal & 255) * (2 * math.pi / 255.0)
                normal = (
                    math.cos(latitude) * math.sin(longitude),
                    math.sin(latitude) * math.sin(longitude),
                    math.cos(longitude),
                )
                # MD3 is Z-up; the viewer is Y-up.
                surface_vertices.append(((x / 64.0, z / 64.0, -y / 64.0),
                                         (normal[0], normal[2], -normal[1])))
            positions.extend(surface_vertices)
            for index in range(triangle_count):
                a, b, c = struct.unpack_from('<3i', raw, surface_cursor + triangle_offset + index * 12)
                if min(a, b, c) < 0 or max(a, b, c) >= vertex_count:
                    raise ValueError('Индекс треугольника MD3 вне диапазона')
                triangles.append((base_vertex + a, base_vertex + b, base_vertex + c))
                if len(triangles) > 200_000:
                    raise OverflowError('Лимит модели — 200000 треугольников')
            surface_names.append(_name(surface_name))
            surface_cursor = local_end
        if surface_cursor != end_offset:
            raise ValueError('Некорректная цепочка поверхностей MD3')

        if not triangles:
            raise ValueError('В MD3 нет треугольников')
        low = [min(vertex[0][axis] for vertex in positions) for axis in range(3)]
        high = [max(vertex[0][axis] for vertex in positions) for axis in range(3)]
        center = [(a + b) / 2 for a, b in zip(low, high)]
        radius = math.sqrt(sum((b - a) ** 2 for a, b in zip(low, high))) / 2
        if radius <= 1e-12:
            raise ValueError('Нулевой размер модели')

        vertices = array('f')
        coordinates = array('f')
        for triangle_index, triangle in enumerate(triangles):
            if context and triangle_index % 1024 == 0:
                context.check()
            for index in triangle:
                point, normal = positions[index]
                vertices.extend(tuple((point[axis] - center[axis]) / radius for axis in range(3)))
                vertices.extend(normal)
                coordinates.extend((*uvs[index], 0.0))

        notices = (f'Показан первый кадр из {frame_count}.',) if frame_count > 1 else ()
        info = {
            'format': 'MD3',
            'model': _name(model_name),
            'frames': frame_count,
            'frame': 0,
            'surfaces': surface_count,
            'objects': surface_count,
            'bytes': len(raw),
            'surface_names': tuple(surface_names),
            'vertices': len(positions),
            'triangles': len(triangles),
        }
        return textured_model(path, context, info, vertices.tobytes(), coordinates.tobytes(), notices)
    except (MemoryError, OverflowError) as exc:
        raise ViewerError('CLAP-RENDER-004', exc, file=path) from exc
    except Exception as exc:
        if isinstance(exc, (AssetFailure, ViewerError)):
            raise
        raise ViewerError('CLAP-RENDER-001', exc, file=path) from exc


class Md3Loader:
    def probe(self, header):
        return header.startswith(MD3_IDENT)

    def load(self, path, context):
        return _load_md3(path, context)
