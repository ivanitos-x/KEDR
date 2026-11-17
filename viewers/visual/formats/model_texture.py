"""Local skin lookup shared by the MD2 and MD3 importers."""
from pathlib import PurePosixPath

from ...core import ViewerError
from ..contracts import Asset, MaterialData, MaterialOp, RasterData, SceneData

FORMATS = {'.jpg': b'jpeg', '.jpeg': b'jpeg', '.png': b'png'}


def _texture_path(path, context, skin_names):
    stems = [path.stem.casefold()]
    for name in skin_names:
        stem = PurePosixPath(name.replace('\\', '/')).stem.casefold()
        if stem and stem not in stems:
            stems.append(stem)
    priority = {stem: index for index, stem in enumerate(stems)}
    extensions = {extension: index for index, extension in enumerate(FORMATS)}
    best = None
    for index, candidate in enumerate(path.parent.iterdir()):
        if context and index % 256 == 0:
            context.check()
        extension = candidate.suffix.casefold()
        stem = candidate.stem.casefold()
        if (extension in extensions and stem in priority and candidate.is_file()
                and candidate.resolve().parent == path.parent):
            key = (priority[stem], extensions[extension], candidate.name)
            if best is None or key < best[0]:
                best = key, candidate
    return best[1] if best else None


def _read_texture(path):
    from PySide6.QtGui import QImage, QImageReader

    if path.stat().st_size > 16 * 1024 * 1024:
        raise OverflowError('Лимит файла текстуры — 16 МиБ')
    reader = QImageReader(str(path), FORMATS[path.suffix.casefold()])
    reader.setAutoDetectImageFormat(False)
    size = reader.size()
    if not size.isValid() or size.isEmpty():
        raise ValueError('Не удалось прочитать заголовок текстуры')
    if size.width() > 8192 or size.height() > 8192 or size.width() * size.height() > 16_000_000:
        raise OverflowError('Размер текстуры превышает лимит 16 миллионов пикселей')
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or 'Не удалось прочитать текстуру')
    has_alpha = image.hasAlphaChannel()
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return RasterData(image.bits().tobytes(), image.width(), image.height(), has_alpha)


def textured_model(path, context, info, vertices, coordinates, notices=(), *, skin_names=()):
    path = path.resolve()
    texture_path = _texture_path(path, context, skin_names)
    texture = None
    if texture_path is not None:
        try:
            texture = _read_texture(texture_path)
        except (MemoryError, OverflowError) as exc:
            raise ViewerError('CLAP-RENDER-004', exc, file=texture_path) from exc
        except (OSError, ValueError) as exc:
            raise ViewerError('CLAP-RENDER-001', exc, file=texture_path) from exc
    info = dict(info, texture=str(texture_path) if texture else '',
                texture_bytes=len(texture.pixels) if texture else 0)
    capabilities = {'view.move', 'view.zoom', 'view.rotate'}
    if texture is None:
        message = 'Рядом с моделью не найдена текстура PNG, JPG или JPEG.'
        return Asset(SceneData(vertices, info), frozenset(capabilities), info,
                     (*notices, message))
    material = MaterialData(
        texture_path.name,
        (MaterialOp('texture'), MaterialOp('constant', values=(0.7,) * 4),
         MaterialOp('constant', values=(0.0,) * 4)),
        0, 1, 2, texture=texture,
    )
    scene = SceneData(vertices, info, (material,), (0,) * info['triangles'], coordinates)
    capabilities.add('view.materials')
    return Asset(scene, frozenset(capabilities), info,
                 (*notices, f'Текстура: {texture_path.name}'), preferred_mode='materials')
