"""Read-only index for the Build Engine KenSilverman archive format."""
from dataclasses import dataclass
from pathlib import Path
import struct

MAX_GRP_ENTRIES = 65_536
_HEADER = struct.Struct('<12sI')
_RECORD = struct.Struct('<12sI')


@dataclass(frozen=True)
class GrpEntry:
    name: str
    path: Path
    entry_index: int
    offset: int
    size: int


def read_grp(path: Path, context=None) -> tuple[GrpEntry, ...]:
    """Validate the catalog and payload ranges without extracting any entry."""
    with path.open('rb') as stream:
        stream.seek(0, 2)
        length = stream.tell()
        stream.seek(0)
        header = stream.read(_HEADER.size)
        if len(header) != _HEADER.size:
            raise ValueError('Оборван заголовок GRP.')
        magic, count = _HEADER.unpack(header)
        if magic != b'KenSilverman':
            raise ValueError('Ожидается архив Build Engine GRP с сигнатурой KenSilverman.')
        if count > MAX_GRP_ENTRIES:
            raise OverflowError('Превышен лимит числа записей GRP.')
        offset = _HEADER.size + count * _RECORD.size
        if offset > length:
            raise ValueError('Оборван каталог GRP.')
        entries = []
        for index in range(count):
            if context and index % 256 == 0:
                context.check()
            record = stream.read(_RECORD.size)
            if len(record) != _RECORD.size:
                raise ValueError('Оборвана запись каталога GRP.')
            raw_name, size = _RECORD.unpack(record)
            if offset + size > length:
                raise ValueError(f'Оборваны данные записи GRP с индексом {index}.')
            name = raw_name.split(b'\0', 1)[0].decode('cp437')
            entries.append(GrpEntry(name, path, index, offset, size))
            offset += size
    return tuple(entries)
