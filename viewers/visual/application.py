"""Open use case; no suffix-specific logic or Qt dependencies."""
from pathlib import Path
from .contracts import LoadContext, AssetFailure

class OpenAsset:
    def __init__(self,registry): self.registry=registry
    def __call__(self,path,context=None):
        context=context or LoadContext()
        context.check()
        path=Path(path).resolve()
        try:
            with path.open('rb') as stream: header=stream.read(16)
            descriptor,loader=self.registry.resolve(path.suffix.lower(),header)
            if path.stat().st_size>descriptor.limits['input_bytes']:
                raise AssetFailure('invalid_input','CLAP-RENDER-004','Превышен лимит размера файла')
            context.progress('Загрузка геометрии / изображения…')
            result=loader.load(path,context)
            context.check()
            return result
        except AssetFailure as exc:
            exc.file=str(path)
            raise
        except OSError as exc:
            failure=AssetFailure('failed','CLAP-FILE-001',str(exc)); failure.file=str(path)
            raise failure from exc
