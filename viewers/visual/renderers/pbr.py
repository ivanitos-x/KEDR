"""Cook–Torrance metallic/roughness adapter over shared scene ownership."""
from dataclasses import replace
from ..contracts import SceneData,MaterialData,MaterialOp
from .gl_scene import SceneGLRenderer

def default_material():
    return MaterialData('Default PBR',(MaterialOp('constant',values=(.5,.5,.5,1)),MaterialOp('constant',values=(.5,)*4),MaterialOp('constant',values=(0,)*4)),0,1,2)

def prepare_scene(scene):
    if not isinstance(scene,SceneData): raise ValueError('PBR требует SceneData')
    count=len(scene.vertices)//72
    if scene.materials:
        if -1 not in scene.material_ids: return scene
        fallback=len(scene.materials)
        return replace(scene,materials=scene.materials+(default_material(),),material_ids=tuple(fallback if i<0 else i for i in scene.material_ids))
    return replace(scene,materials=(default_material(),),material_ids=(0,)*count,coordinates=bytes(count*36))

class PbrRenderer(SceneGLRenderer):
    allowed_modes=('pbr',)
    def __init__(self,scene):
        self.environment_texture=None; self.environment_size=None
        super().__init__(prepare_scene(scene))
    def material_source(self,material):
        from .material_shader import VERTEX,fragment_shader
        from .pbr_shader import lighting_source
        return VERTEX,fragment_shader(material,lighting_source)
    def set_environment(self,data):
        from PySide6.QtGui import QImage
        from PySide6.QtOpenGL import QOpenGLTexture
        if data is not None and (not 1<=data.width<=2048 or not 1<=data.height<=1024 or len(data.rgbe)!=data.width*data.height*4): raise ValueError('Неверное окружение RGBE')
        if not self.context.makeCurrent(self.surface): raise ValueError('Потерян OpenGL context')
        new=None
        try:
            if data is not None:
                image=QImage(data.rgbe,data.width,data.height,data.width*4,QImage.Format.Format_RGBA8888).copy()
                new=QOpenGLTexture(image,QOpenGLTexture.MipMapGeneration.DontGenerateMipMaps)
                if not new.isCreated(): raise ValueError('Не удалось создать HDR texture')
                new.setMinMagFilters(QOpenGLTexture.Filter.Nearest,QOpenGLTexture.Filter.Nearest)
                new.setWrapMode(QOpenGLTexture.CoordinateDirection.DirectionS,QOpenGLTexture.WrapMode.Repeat)
                new.setWrapMode(QOpenGLTexture.CoordinateDirection.DirectionT,QOpenGLTexture.WrapMode.ClampToEdge)
            old=self.environment_texture; self.environment_texture=new; self.environment_size=(data.width,data.height) if data else None
            if old: old.destroy()
        except BaseException:
            if new and new is not self.environment_texture: new.destroy()
            raise
        finally: self.context.doneCurrent()
    def configure_program(self,program):
        if program.uniformLocation('has_environment')>=0:
            program.setUniformValue(program.uniformLocation('has_environment'),int(self.environment_texture is not None))
            if self.environment_texture:
                from PySide6.QtGui import QVector2D
                program.setUniformValue(program.uniformLocation('hdr_environment'),0)
                program.setUniformValue('environment_size',QVector2D(*self.environment_size))
                self.environment_texture.bind(0)
    def close(self):
        if getattr(self,'environment_texture',None) and getattr(self,'context',None) and self.context.makeCurrent(self.surface):
            self.environment_texture.destroy(); self.environment_texture=None; self.context.doneCurrent()
        super().close()
