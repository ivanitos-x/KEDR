"""Controller-owned composition root. New formats are registered here only."""
from .contracts import Descriptor,RasterData,SceneData,AssetFailure,DisplayMode
from .registry import Registry
from .application import OpenAsset

def qt_loader():
    from .formats.qt_raster import QtRasterLoader
    return QtRasterLoader()
def art_loader():
    from .formats.art import ArtLoader
    return ArtLoader()
def art_window(path,asset):
    from .art_viewer import ArtWindow
    return ArtWindow(path,asset)
def glb_loader():
    from .formats.glb import GlbLoader
    return GlbLoader()
def kvx_loader():
    from .formats.kvx import KvxLoader
    return KvxLoader()
def md3_loader():
    from .formats.md3 import Md3Loader
    return Md3Loader()
def md2_loader():
    from .formats.md2 import Md2Loader
    return Md2Loader()
def blend_loader(subdivision=None):
    from .formats.blend import BlendLoader
    return BlendLoader(subdivision)
def subdivision_modifier():
    from .subdivision import SubdivisionModifier
    return SubdivisionModifier()
def solid_renderer(vertices):
    from .renderers.solid_gl import SolidRenderer
    return SolidRenderer(vertices)
def pbr_renderer(scene):
    from .renderers.pbr import PbrRenderer
    return PbrRenderer(scene)
def radiance_loader():
    from .environment import RadianceLoader
    return RadianceLoader()
def load_environment(path,context=None):
    registry=build_registry()
    return registry.operation('visual.environment-loader',path.suffix.lower()).factory().load(path,context)

def build_registry():
    selected=frozenset({'file.read.selected'})
    sibling_texture=frozenset({'file.read.sibling-model-texture'})
    art_files=frozenset({'file.read.sibling-art','file.read.build-palette'})
    registry=Registry(grants=selected|sibling_texture|art_files)
    renderer='clap.visual.renderer.solid'
    modifier='clap.visual.modifier.subdivision'
    tile_window='clap.visual.window.art'
    registry.register(Descriptor(tile_window,'1.0.0','visual.asset-window','1.0',frozenset({'view.tile-grid'}),('view.tile-grid',),(),{},frozenset(),art_window))
    registry.register(Descriptor(modifier,'1.0.0','visual.mesh-modifier','1.0',frozenset({'mesh.subdivision'}),('subdivision',),(),{'triangles':200000,'levels':6},frozenset(),subdivision_modifier))
    registry.register(Descriptor(renderer,'1.1.0','visual.scene-renderer','1.0',frozenset({'scene.solid','scene.material-preview'}),('solid','materials'),(),{'frame_side':640},frozenset(),solid_renderer,modes=(DisplayMode('solid','Solid'),DisplayMode('materials','Материалы (приближённо)',True))))
    registry.register(Descriptor('clap.visual.renderer.pbr','1.0.0','visual.scene-renderer','1.0',frozenset({'scene.pbr','scene.environment'}),('pbr',),(),{'frame_side':640,'ibl_samples':16},frozenset(),pbr_renderer,modes=(DisplayMode('pbr','PBR'),)))
    registry.register(Descriptor('clap.visual.environment.radiance','1.0.0','visual.environment-loader','1.0',frozenset({'environment.hdr'}),('.hdr',),(),{'input_bytes':16*1024*1024,'pixels':2048*1024},frozenset({'file.read.selected'}),radiance_loader))
    for key,factory,extensions,caps,requires,permissions in [
        ('qt-raster',qt_loader,('.png',),{'raster.decode'},(),selected),
        ('art',art_loader,('.art',),{'tile.decode'},(tile_window,),selected|art_files),
        ('glb',glb_loader,('.glb',),{'scene.decode'},(renderer,),selected),
        ('blend-native',lambda:blend_loader(registry.operation('visual.mesh-modifier','subdivision').factory()),('.blend',),{'scene.decode','material.decode.preview'},(renderer,modifier),selected),
        ('kvx',kvx_loader,('.kvx',),{'scene.decode','material.decode.preview'},(renderer,),selected),
        ('md3',md3_loader,('.md3',),{'scene.decode','material.decode.preview'},(renderer,),selected|sibling_texture),
        ('md2',md2_loader,('.md2',),{'scene.decode','material.decode.preview'},(renderer,),selected|sibling_texture),
    ]:
        registry.register(Descriptor('clap.visual.format.'+key,'1.0.0','visual.asset-loader','1.0',frozenset(caps),extensions,requires,{'input_bytes':64*1024*1024,'timeout_seconds':30,'triangles':200000,'decoded_bytes':128*1024*1024},permissions,factory))
    registry.validate()
    return registry

def open_asset(path,context=None): return OpenAsset(build_registry())(path,context)

def open_art_archive(path,entry_index,context):
    from .formats.art import load_art_asset
    context.check()
    context.progress('Чтение каталога GRP…')
    result=load_art_asset(path,context,entry_index=entry_index)
    context.check()
    return result

def file_filter():
    return 'KEDR ('+' '.join('*'+ext for ext in build_registry().extensions())+')'

def create_asset_window(path,asset):
    registry=build_registry()
    for descriptor in registry.entries.values():
        if descriptor.contract_id=='visual.asset-window' and not registry.reason(descriptor.module_id):
            for capability in descriptor.accepts:
                if capability in asset.capabilities:
                    return registry.operation('visual.asset-window',capability).factory(path,asset)
    return None

def create_presentation(asset):
    """Create GUI resources in the GUI thread, after loading domain data."""
    from PySide6.QtGui import QImage
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication
    data=asset.data
    if isinstance(data,SceneData):
        registry=build_registry()
        from .presentation import RendererSession
        renderer=RendererSession(data,registry)
        screen=QApplication.primaryScreen().availableGeometry(); side=min(640,screen.width()*3//4,screen.height()*3//4)
        try:
            if asset.preferred_mode!='solid': renderer.set_display_mode(asset.preferred_mode)
            return renderer.render(QSize(side,side),0,0,1),renderer
        except BaseException:
            try: renderer.close()
            except Exception: pass
            raise
    if isinstance(data,RasterData):
        image=QImage(data.pixels,data.width,data.height,data.width*4,QImage.Format.Format_RGBA8888).copy()
        if not data.has_alpha: image=image.convertToFormat(QImage.Format.Format_RGB32)
        return image,None
    raise AssetFailure('unsupported','CLAP-RENDER-005','Неизвестный тип результата загрузчика')
