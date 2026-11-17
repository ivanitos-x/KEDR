"""Domain and ports; no Qt, filesystem implementation, plugins or bootstrap."""
from dataclasses import dataclass, field
from typing import Protocol, Callable, TYPE_CHECKING
from threading import Event
from pathlib import Path
import time

if TYPE_CHECKING:
    from .formats.art import ArtData

@dataclass(frozen=True)
class MaterialOp:
    operation: str
    inputs: tuple[int, ...] = ()
    values: tuple[float, ...] = ()

@dataclass(frozen=True)
class MaterialData:
    name: str
    nodes: tuple[MaterialOp, ...]
    color: int
    roughness: int
    metallic: int
    notices: tuple[str, ...] = ()
    texture: 'RasterData | None' = None

@dataclass(frozen=True)
class Triangle:
    positions: tuple
    coordinates: tuple
    material: int = -1
    normals: tuple = ()

@dataclass(frozen=True)
class PolygonMesh:
    positions: tuple
    faces: tuple
    materials: tuple[int, ...]
    normals: tuple = ()

@dataclass(frozen=True)
class SubdivisionSettings:
    levels: int
    algorithm: str = 'catmull-clark'
    preserve_boundary_corners: bool = False

@dataclass(frozen=True)
class ModifiedMesh:
    mesh: PolygonMesh
    levels: int
    notices: tuple[str, ...] = ()

class MeshModifier(Protocol):
    def apply(self,mesh: PolygonMesh,settings: SubdivisionSettings,context) -> ModifiedMesh: ...

@dataclass(frozen=True)
class SceneData:
    vertices: bytes  # float32 position + flat normal, six floats per vertex
    info: dict
    materials: tuple[MaterialData, ...] = ()
    material_ids: tuple[int, ...] = ()
    coordinates: bytes = b''  # three float32 per vertex: generated coordinates or (u, v, 0)

@dataclass(frozen=True)
class RasterData:
    pixels: bytes  # RGBA8888, straight alpha
    width: int
    height: int
    has_alpha: bool

@dataclass(frozen=True)
class Asset:
    data: 'SceneData | RasterData | ArtData'
    capabilities: frozenset[str]
    info: dict
    notices: tuple[str, ...] = ()
    preferred_mode: str = 'solid'

class AssetFailure(ValueError):
    def __init__(self, status, code, detail):
        self.status, self.code, self.detail = status, code, detail
        super().__init__(f'{code}: {detail}')

@dataclass
class LoadContext:
    cancel: Event = field(default_factory=Event)
    timeout: float = 30
    progress: Callable[[str], None] = lambda _: None
    started: float = field(default_factory=time.monotonic)
    palette_path: Path | None = None
    def check(self):
        if self.cancel.is_set(): raise AssetFailure('cancelled','CLAP-RENDER-007','Открытие отменено')
        if time.monotonic()-self.started>=self.timeout: raise AssetFailure('failed','CLAP-RENDER-008','Истёк бюджет загрузки')

class AssetLoader(Protocol):
    def probe(self, header: bytes) -> bool: ...
    def load(self, path: Path, context: LoadContext) -> Asset: ...

class SceneRenderer(Protocol):
    def render(self, size, yaw: float, pitch: float, zoom: float): ...
    def close(self) -> None: ...

class MaterialPreview(Protocol):
    """Optional port, advertised only by view.materials capability."""
    def set_display_mode(self, mode: str) -> None: ...

@dataclass(frozen=True)
class DisplayMode:
    key: str
    label: str
    requires_materials: bool = False

@dataclass(frozen=True)
class Descriptor:
    module_id: str
    module_version: str
    contract_id: str
    api_version: str
    provides: frozenset[str]
    accepts: tuple[str, ...]
    requires: tuple[str, ...]
    limits: dict
    permissions: frozenset[str]
    factory: Callable[..., object]
    priority: int = 0
    unavailable: str = ''
    modes: tuple[DisplayMode, ...] = ()
