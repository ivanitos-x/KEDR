"""Copy notices for the libraries shipped in the Windows bundle."""
from importlib.metadata import distribution
from pathlib import Path
from shutil import copy2
import sys


def main(destination):
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent
    for name in ('GPL-3.0.txt', 'LGPL-3.0.txt'):
        copy2(source / 'licenses' / name, output)
    copy2(source / 'THIRD-PARTY.md', output)
    copy2(Path(sys.base_prefix) / 'LICENSE.txt', output / 'Python-LICENSE.txt')
    for package in ('PySide6', 'PySide6-Essentials', 'PySide6-Addons', 'shiboken6',
                    'zstandard', 'PyInstaller'):
        metadata = distribution(package)
        for path in metadata.files or ():
            if path.name.lower().startswith(('license', 'copying', 'notice')):
                copy2(metadata.locate_file(path), output / f'{package}-{path.name}')


if __name__ == '__main__':
    main(sys.argv[1])
