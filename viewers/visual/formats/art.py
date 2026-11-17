"""Bounded reader for Build ART tile files and their picanm animation links."""
from dataclasses import dataclass, field
from pathlib import Path
import struct

from ...core import ViewerError
from ..contracts import Asset, AssetFailure
from .grp import GrpEntry, read_grp

MAX_ART_BYTES = 64 * 1024 * 1024
MAX_TILES = 65_536
MAX_TILE_SIDE = 8_192
MAX_DECODED_PIXELS = 128 * 1024 * 1024
MAX_SIBLING_FILES = 128
MAX_SIBLING_METADATA = 8 * 1024 * 1024
HEADER_SIZE = 16


@dataclass(frozen=True)
class ArtTile:
    tile_id: int
    width: int
    height: int
    pixels: bytes
    picanm: int


@dataclass(frozen=True)
class ArtEntry:
    name: str
    path: Path
    entry_index: int | None
    offset: int
    size: int


@dataclass
class _ArtSource:
    entry: ArtEntry | GrpEntry
    start_tile: int
    end_tile: int
    dimensions: tuple[tuple[int, int], ...]
    picanm: tuple[int, ...]
    pixels_offset: int
    size: int


@dataclass
class ArtData:
    tiles: dict[int, ArtTile]
    frames: dict[int, ArtTile]
    palette: bytes | None
    _sources: dict[int, _ArtSource] = field(default_factory=dict, repr=False)
    _decoded_pixels: int = field(default=0, repr=False)
    missing: set[int] = field(default_factory=set, repr=False)
    entries: tuple[ArtEntry | GrpEntry, ...] = ()
    position: int = 0
    palette_source: str = ''
    palette_issue: str = ''

    def prime_animations(self, context=None) -> None:
        """Decode reachable animation frames while the selected file is loading."""
        requests = set()
        for tile in self.tiles.values():
            frame_count = tile.picanm & 0x3F
            animation_type = (tile.picanm >> 6) & 0x03
            if not frame_count or not animation_type:
                continue
            for step in range(frame_count + 1):
                if animation_type == 3:
                    requests.add(tile.tile_id - step)
                else:
                    requests.add(tile.tile_id + step)
            if animation_type == 1:
                requests.update(tile.tile_id + step for step in range(frame_count + 1))
        for tile_id in sorted(requests):
            if context:
                context.check()
            if self._load_frame(tile_id, context) is None:
                self.missing.add(tile_id)

    def frame(self, tile_id: int, ticks: int) -> int | None:
        """Return the Build animation tile active at 120 Hz Build ticks."""
        if type(tile_id) is not int or type(ticks) is not int or ticks < 0:
            return None
        base = self.frames.get(tile_id)
        if base is None:
            return None
        frame_count = base.picanm & 0x3F
        animation_type = (base.picanm >> 6) & 0x03
        speed = (base.picanm >> 24) & 0x0F
        if not frame_count or not animation_type:
            return tile_id
        animation_tick = ticks >> speed
        if animation_type == 1:
            phase = animation_tick % (frame_count * 2)
            offset = phase if phase < frame_count else frame_count * 2 - phase
        elif animation_type == 2:
            offset = animation_tick % (frame_count + 1)
        else:
            offset = -(animation_tick % (frame_count + 1))
        target = tile_id + offset
        if target not in self.frames:
            return None
        return target

    def _load_frame(self, tile_id: int, context=None) -> ArtTile | None:
        if tile_id in self.frames:
            return self.frames[tile_id]
        source = self._sources.get(tile_id)
        if source is None:
            return None
        if context:
            context.check()
        offset = tile_id - source.start_tile
        width, height = source.dimensions[offset]
        if not width or not height:
            return None
        pixel_count = width * height
        if self._decoded_pixels + pixel_count > MAX_DECODED_PIXELS:
            return None
        try:
            with source.entry.path.open('rb') as stream:
                pixel_offset = source.pixels_offset + sum(
                    w * h for w, h in source.dimensions[:offset])
                stream.seek(source.entry.offset + pixel_offset)
                column_pixels = stream.read(pixel_count)
        except OSError:
            return None
        if len(column_pixels) != pixel_count:
            return None
        pixels = _transpose(column_pixels, width, height, context)
        tile = ArtTile(tile_id, width, height, pixels, source.picanm[offset])
        self.frames[tile_id] = tile
        self._decoded_pixels += pixel_count
        return tile


def _read_palette(entry: ArtEntry | GrpEntry) -> bytes:
    if entry.size < 768:
        raise ValueError('Палитра содержит меньше 768 байт.')
    with entry.path.open('rb') as stream:
        stream.seek(entry.offset)
        palette = stream.read(768)
    if len(palette) != 768 or max(palette, default=0) > 63:
        raise ValueError('PALETTE.DAT должна начинаться с 768 байт RGB VGA (0–63).')
    return palette


def _transpose(column_pixels: bytes, width: int, height: int, context=None) -> bytes:
    if width < 2 or height < 2:
        return column_pixels
    rows = bytearray(len(column_pixels))
    for x in range(width):
        if context and x % 128 == 0:
            context.check()
        source = x * height
        for y in range(height):
            rows[y * width + x] = column_pixels[source + y]
    return bytes(rows)


def _read_source(entry: ArtEntry | GrpEntry, *, decode_pixels: bool,
                 context=None) -> tuple[_ArtSource, dict[int, ArtTile]]:
    size = entry.size
    if size > MAX_ART_BYTES:
        raise OverflowError('Лимит одного ART-файла — 64 МиБ.')
    if size < HEADER_SIZE:
        raise ValueError('Оборван заголовок ART.')
    with entry.path.open('rb') as stream:
        stream.seek(entry.offset)
        header = stream.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE:
            raise ValueError('Оборван заголовок ART.')
        version, tile_count, start_tile, end_tile = struct.unpack('<4i', header)
        if version != 1:
            raise ValueError('Поддерживается ART версии 1.')
        if (not 1 <= tile_count <= MAX_TILES or start_tile < 0
                or end_tile < start_tile or end_tile >= MAX_TILES):
            raise ValueError('Некорректный диапазон тайлов ART.')
        tile_count = end_tile - start_tile + 1
        dimension_bytes = tile_count * 4
        pixels_offset = HEADER_SIZE + dimension_bytes + tile_count * 4
        if pixels_offset > size:
            raise ValueError('Оборваны таблицы размеров или picanm ART.')
        dimensions_raw = stream.read(dimension_bytes)
        picanm_raw = stream.read(tile_count * 4)
        if len(dimensions_raw) != dimension_bytes or len(picanm_raw) != tile_count * 4:
            raise ValueError('Оборваны таблицы размеров или picanm ART.')
        widths = struct.unpack(f'<{tile_count}H', dimensions_raw[:tile_count * 2])
        heights = struct.unpack(f'<{tile_count}H', dimensions_raw[tile_count * 2:])
        dimensions = []
        pixel_bytes = 0
        for width, height in zip(widths, heights):
            if width > MAX_TILE_SIDE or height > MAX_TILE_SIDE:
                raise OverflowError('Размер тайла ART превышает 8192 пикселя по стороне.')
            pixel_bytes += width * height
            if pixel_bytes > MAX_DECODED_PIXELS:
                raise OverflowError('Суммарный размер тайлов ART превышает 128 млн пикселей.')
            dimensions.append((width, height))
        picanm = struct.unpack(f'<{tile_count}I', picanm_raw)
        if pixels_offset + pixel_bytes != size:
            raise ValueError('Длины блоков ART не совпадают с размером файла.')
        source = _ArtSource(entry, start_tile, end_tile, tuple(dimensions), tuple(picanm),
                            pixels_offset, size)
        tiles: dict[int, ArtTile] = {}
        if decode_pixels:
            for index, (width, height) in enumerate(dimensions):
                if context:
                    context.check()
                length = width * height
                column_pixels = stream.read(length)
                if len(column_pixels) != length:
                    raise ValueError('Оборваны пиксели ART.')
                pixels = _transpose(column_pixels, width, height, context)
                tile_id = start_tile + index
                if width and height:
                    tiles[tile_id] = ArtTile(tile_id, width, height, pixels, picanm[index])
        return source, tiles


def _loose_entry(path: Path) -> ArtEntry:
    return ArtEntry(path.name, path, None, 0, path.stat().st_size)


def _loose_siblings(path: Path, context):
    try:
        candidates = sorted(path.parent.iterdir(), key=lambda item: (item.name.casefold(), item.name))
    except OSError:
        return
    for candidate in candidates:
        if context:
            context.check()
        if candidate.suffix.casefold() != '.art':
            continue
        try:
            real = candidate.resolve()
            if real != path and real.parent == path.parent and real.is_file():
                yield _loose_entry(real)
        except (OSError, RuntimeError):
            continue


def _inventory(siblings, selected: _ArtSource, context):
    catalog = [selected]
    metadata_bytes = 0
    for count, sibling in enumerate(siblings):
        if count >= MAX_SIBLING_FILES:
            break
        if context:
            context.check()
        try:
            source, _ = _read_source(sibling, decode_pixels=False, context=context)
        except AssetFailure:
            raise
        except (OSError, ValueError, OverflowError):
            continue
        metadata_bytes += HEADER_SIZE + len(source.dimensions) * 8
        if metadata_bytes > MAX_SIBLING_METADATA:
            break
        catalog.append(source)
    catalog.sort(key=lambda item: (item.start_tile, item.entry.name.casefold(),
                                  item.entry.name, item.entry.entry_index or 0))
    entries = tuple(item.entry for item in catalog)
    sources = {}
    for item in (selected, *catalog):
        for tile_id in range(item.start_tile, item.end_tile + 1):
            sources.setdefault(tile_id, item)
    return entries, entries.index(selected.entry), sources


def _select_palette(path, context, archive):
    issue = []
    explicit = getattr(context, 'palette_path', None)
    if explicit:
        explicit = Path(explicit).resolve()
        try:
            return _read_palette(_loose_entry(explicit)), str(explicit), ''
        except (OSError, ValueError):
            issue.append(f'Указанная палитра недоступна или повреждена: {explicit}.')
    if archive is None:
        palette_path = path.parent / 'PALETTE.DAT'
        try:
            return _read_palette(_loose_entry(palette_path)), str(palette_path), ''
        except FileNotFoundError:
            issue.append('Рядом с ART нет PALETTE.DAT.')
        except (OSError, ValueError):
            issue.append('Соседняя PALETTE.DAT недоступна или повреждена.')
    else:
        for entry in archive:
            if entry.name.casefold() == 'palette.dat':
                try:
                    return _read_palette(entry), f'{path.name} → {entry.name}', ''
                except (OSError, ValueError):
                    continue
        issue.append('В GRP нет читаемой PALETTE.DAT.')
    saved = getattr(context, 'saved_palette_path', None)
    if saved:
        saved = Path(saved).resolve()
        try:
            return _read_palette(_loose_entry(saved)), str(saved), ''
        except (OSError, ValueError):
            issue.append(f'Сохранённая палитра недоступна или повреждена: {saved}.')
    return None, '', ' '.join(issue)


def load_art(path, context=None, entry_index=None):
    path = Path(path).resolve()
    try:
        if context:
            context.check()
        archive = None
        if entry_index is None:
            entry = _loose_entry(path)
            siblings = _loose_siblings(path, context)
        else:
            archive = read_grp(path, context)
            if not 0 <= entry_index < len(archive):
                raise ValueError(f'Недопустимый индекс записи GRP: {entry_index}.')
            entry = archive[entry_index]
            if not entry.name.casefold().endswith('.art'):
                raise ValueError(f'Запись GRP с индексом {entry_index} не является ART.')
            siblings = (item for item in archive if item.entry_index != entry_index
                        and item.name.casefold().endswith('.art'))
        source, tiles = _read_source(entry, decode_pixels=True, context=context)
        palette, palette_source, palette_issue = _select_palette(path, context, archive)
        entries, position, sources = _inventory(siblings, source, context)
        data = ArtData(
            tiles, dict(tiles), palette, sources,
            sum(tile.width * tile.height for tile in tiles.values()),
            entries=entries, position=position, palette_source=palette_source,
            palette_issue=palette_issue,
        )
        data.prime_animations(context)
        return data
    except (MemoryError, OverflowError) as exc:
        raise ViewerError('CLAP-RENDER-004', exc, file=path) from exc
    except Exception as exc:
        if isinstance(exc, (ViewerError, AssetFailure)):
            raise
        raise ViewerError('CLAP-RENDER-001', exc, file=path) from exc


def load_art_asset(path, context=None, entry_index=None):
    data = load_art(path, context, entry_index)
    current = data.entries[data.position]
    info = {
        'format': 'Build ART',
        'tiles': len(data.tiles),
        'tile_start': min(data.tiles, default=0),
        'tile_end': max(data.tiles, default=0),
        'palette': data.palette is not None,
        'bytes': current.size,
    }
    return Asset(data, frozenset({'view.tile-grid', 'art.animation'}), info)


class ArtLoader:
    def probe(self, header):
        if len(header) < HEADER_SIZE:
            return False
        version, tile_count, start_tile, end_tile = struct.unpack('<4i', header[:HEADER_SIZE])
        return (version == 1 and 1 <= tile_count <= MAX_TILES and start_tile >= 0
                and end_tile >= start_tile and end_tile < MAX_TILES
                and end_tile - start_tile + 1 <= MAX_TILES)

    def load(self, path, context):
        return load_art_asset(path, context)
