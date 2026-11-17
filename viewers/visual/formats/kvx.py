"""Bounded reader for Ken Silverman's Build KVX voxel format."""
from array import array
import math
import struct
from pathlib import Path

from ...core import ViewerError
from ..contracts import MaterialData, MaterialOp
from ..palette import palette_raster

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TRIANGLES = 200_000
MAX_VOXELS = 2_000_000


def read_kvx(path, context=None):
    try:
        path = Path(path)
        if context:
            context.check()
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise OverflowError('Лимит KVX — 64 МиБ')
        if len(raw) < 4 + 24 + 768:
            raise ValueError('Файл KVX слишком короткий')

        palette_start = len(raw) - 768
        if len(raw[palette_start:]) != 768:
            raise ValueError('Оборвана палитра KVX')
        palette = palette_raster(raw[palette_start:])

        mip_offset = 0
        first_mip = None
        while mip_offset < palette_start:
            if mip_offset + 4 > palette_start:
                raise ValueError('Оборван заголовок уровня KVX')
            byte_count = struct.unpack_from('<I', raw, mip_offset)[0]
            mip_end = mip_offset + 4 + byte_count
            if byte_count < 24 or mip_end > palette_start:
                raise ValueError('Размер уровня KVX выходит за границы файла')
            if first_mip is None:
                first_mip = (mip_offset, mip_end, byte_count)
            mip_offset = mip_end
            if context:
                context.check()
        if mip_offset != palette_start or first_mip is None:
            raise ValueError('Некорректная граница mip-уровней KVX')

        mip_offset, mip_end, byte_count = first_mip
        xs, ys, zs, xp, yp, zp = struct.unpack_from('<6i', raw, mip_offset + 4)
        if not (1 <= xs <= 256 and 1 <= ys <= 256 and 1 <= zs <= 255):
            raise ValueError('Размеры KVX должны быть в пределах 256 × 256 × 255')
        table_bytes = (xs + 1) * 4 + xs * (ys + 1) * 2
        offsets_start = mip_offset + 4 + 24
        data_start = offsets_start + table_bytes
        data_end = mip_end
        if data_start > data_end:
            raise ValueError('Таблицы столбцов KVX обрезаны')
        x_offsets = struct.unpack_from(f'<{xs + 1}I', raw, offsets_start)
        y_start = offsets_start + (xs + 1) * 4
        y_offsets = struct.unpack_from(f'<{xs * (ys + 1)}H', raw, y_start)
        if x_offsets[0] != table_bytes or x_offsets[-1] > data_end - offsets_start:
            raise ValueError('Некорректные смещения столбцов KVX')
        if any(a > b for a, b in zip(x_offsets, x_offsets[1:])):
            raise ValueError('Смещения X KVX должны идти по возрастанию')

        positions = array('f')
        normals = array('f')
        coordinates = array('f')
        material_ids = []
        low = [math.inf] * 3
        high = [-math.inf] * 3
        pivot = (xp / 256.0, yp / 256.0, zp / 256.0)
        triangle_count = 0
        faces = (
            ((-1, 0, 0), 0, ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))),
            ((1, 0, 0), 1, ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
            ((0, -1, 0), 2, ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
            ((0, 1, 0), 3, ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))),
            ((0, 0, -1), 4, ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))),
            ((0, 0, 1), 5, ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
        )

        def append_slab(x, y, z_top, colors, visibility):
            nonlocal triangle_count
            run_length = len(colors)
            for direction, bit, corners in faces:
                if not visibility & (1 << bit):
                    continue
                if bit == 4:
                    segments = ((z_top, z_top, colors[0]),)
                elif bit == 5:
                    segments = ((z_top + run_length, z_top + run_length, colors[-1]),)
                else:
                    runs = []
                    start = 0
                    for index in range(1, run_length + 1):
                        if index == run_length or colors[index] != colors[start]:
                            runs.append((z_top + start, z_top + index, colors[start]))
                            start = index
                    segments = runs

                normal = (direction[0], -direction[2], direction[1])
                for segment_start, segment_end, color_index in segments:
                    triangle_count += 2
                    if triangle_count > MAX_TRIANGLES:
                        raise OverflowError('Лимит KVX — 200 000 треугольников')
                    quad = []
                    for corner in corners:
                        z = segment_end if corner[2] else segment_start
                        point = (x + corner[0] - pivot[0],
                                 -(z - pivot[2]),
                                 y + corner[1] - pivot[1])
                        for axis in range(3):
                            low[axis] = min(low[axis], point[axis])
                            high[axis] = max(high[axis], point[axis])
                        quad.append(point)
                    for triangle in ((0, 1, 2), (0, 2, 3)):
                        for corner_index in triangle:
                            positions.extend(quad[corner_index])
                            normals.extend(normal)
                            coordinates.extend(((color_index + 0.5) / 256.0, 0.5, 0.0))
                        material_ids.append(0)

        voxel_count = 0
        for x in range(xs):
            x_base = x_offsets[x]
            x_limit = x_offsets[x + 1]
            column_offsets = y_offsets[x * (ys + 1):(x + 1) * (ys + 1)]
            if column_offsets[0] != 0 or column_offsets[-1] > x_limit - x_base:
                raise ValueError('Некорректные смещения Y KVX')
            if any(a > b for a, b in zip(column_offsets, column_offsets[1:])):
                raise ValueError('Смещения Y KVX должны идти по возрастанию')
            for y in range(ys):
                cursor = offsets_start + x_base + column_offsets[y]
                end = offsets_start + x_base + column_offsets[y + 1]
                while cursor < end:
                    if cursor + 3 > end:
                        raise ValueError('Оборван заголовок KVX-столбца')
                    z_top, run_length, visibility = struct.unpack_from('<BBB', raw, cursor)
                    cursor += 3
                    if run_length == 0 or z_top + run_length > zs or cursor + run_length > end:
                        raise ValueError('Некорректная длина KVX-слоя')
                    if visibility & 0xC0:
                        raise ValueError('Неизвестные биты видимости KVX')
                    voxel_count += run_length
                    if voxel_count > MAX_VOXELS:
                        raise OverflowError('Лимит KVX — 2 000 000 вокселей')
                    colors = raw[cursor:cursor + run_length]
                    append_slab(x, y, z_top, colors, visibility)
                    cursor += run_length
                if cursor != end:
                    raise ValueError('Некорректная граница KVX-слоя')

        if not triangle_count:
            raise ValueError('В KVX нет видимых поверхностей')
        center = tuple((a + b) / 2 for a, b in zip(low, high))
        radius = math.sqrt(sum((b - a) ** 2 for a, b in zip(low, high))) / 2
        if radius <= 0:
            raise ValueError('Нулевой размер KVX-модели')

        vertices = array('f')
        for offset in range(0, len(positions), 3):
            vertices.extend(((positions[offset] - center[0]) / radius,
                             (positions[offset + 1] - center[1]) / radius,
                             (positions[offset + 2] - center[2]) / radius,
                             *normals[offset:offset + 3]))
        from ..contracts import SceneData
        material = MaterialData(
            'KVX palette',
            (MaterialOp('texture'), MaterialOp('constant', values=(0.8,) * 4),
             MaterialOp('constant', values=(0.0,) * 4)),
            0, 1, 2, texture=palette,
        )
        info = {
            'format': 'KVX',
            'vertices': triangle_count * 3,
            'triangles': triangle_count,
            'voxels': voxel_count,
            'objects': 1,
            'bytes': len(raw),
            'materials': 1,
        }
        return SceneData(vertices.tobytes(), info, (material,), tuple(material_ids),
                         coordinates.tobytes())
    except (MemoryError, OverflowError) as exc:
        raise ViewerError('CLAP-RENDER-004', exc, file=path) from exc
    except Exception as exc:
        from ..contracts import AssetFailure
        if isinstance(exc, AssetFailure):
            raise
        raise ViewerError('CLAP-RENDER-001', exc, file=path) from exc


class KvxLoader:
    def probe(self, header):
        if len(header) < 16:
            return False
        byte_count, xs, ys, zs = struct.unpack_from('<4i', header)
        table_bytes = (xs + 1) * 4 + xs * (ys + 1) * 2
        return (24 + table_bytes <= byte_count <= MAX_FILE_BYTES
                and 1 <= xs <= 256 and 1 <= ys <= 256 and 1 <= zs <= 255)

    def load(self, path, context):
        from ..contracts import Asset
        scene = read_kvx(path, context)
        return Asset(scene, frozenset({'view.move', 'view.zoom', 'view.rotate',
                                       'view.materials', 'view.palette'}),
                     scene.info, preferred_mode='solid')
