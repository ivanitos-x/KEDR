"""Build VGA palettes as a small texture shared by the material renderers."""
from dataclasses import replace
from pathlib import Path

from ..core import ViewerError
from .contracts import RasterData

PALETTE_BYTES = 256 * 3


def palette_raster(raw: bytes) -> RasterData:
    if len(raw) != PALETTE_BYTES or max(raw) > 63:
        raise ValueError('Ожидаются 256 цветов VGA с компонентами от 0 до 63.')
    rgba = bytearray()
    for offset in range(0, PALETTE_BYTES, 3):
        rgba.extend(round(component * 255 / 63) for component in raw[offset:offset + 3])
        rgba.append(255)
    return RasterData(bytes(rgba), 256, 1, False)


def replace_palette(asset, path):
    path = Path(path)
    if 'view.palette' not in asset.capabilities:
        raise ViewerError('CLAP-RENDER-005', 'Этот файл не поддерживает замену палитры.', file=path)
    try:
        with path.open('rb') as stream:
            texture = palette_raster(stream.read(PALETTE_BYTES))
    except OSError as exc:
        raise ViewerError('CLAP-FILE-001', exc, file=path) from exc
    except ValueError as exc:
        raise ViewerError('CLAP-RENDER-001', exc, file=path) from exc
    material, = asset.data.materials
    scene = replace(asset.data, materials=(replace(material, texture=texture),))
    return replace(asset, data=scene, notices=(*asset.notices, f'Палитра: {path.name}'))
