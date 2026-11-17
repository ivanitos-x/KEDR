from ...core import ViewerError

class SceneGLRenderer:
    allowed_modes=('solid','materials')
    def material_source(self,material):
        from .material_shader import VERTEX,fragment_shader
        return VERTEX,fragment_shader(material)
    def configure_program(self,program): pass
    """Render on change into RGBA FBO; use the existing translucent QWidget compositor."""
    def __init__(self,vertices):
        try: self._initialize(vertices)
        except BaseException:
            try: self.close()
            except Exception: pass
            raise

    def _initialize(self,vertices):
        from ..contracts import SceneData
        scene=vertices if isinstance(vertices,SceneData) else None
        if scene is not None: vertices=scene.vertices
        self.materials=scene.materials if scene else ()
        self.material_programs=[]; self.textures={}; self.display_mode='solid'; self.groups=[]; self.coordinate_buffer=None
        from PySide6.QtGui import QOpenGLContext, QOffscreenSurface, QSurfaceFormat
        from PySide6.QtOpenGL import QOpenGLShaderProgram, QOpenGLShader, QOpenGLBuffer
        self.context=QOpenGLContext(); fmt=QSurfaceFormat(); fmt.setVersion(2,1); fmt.setAlphaBufferSize(8); fmt.setDepthBufferSize(24)
        self.context.setFormat(fmt)
        self.surface=QOffscreenSurface(); self.surface.setFormat(fmt); self.surface.create()
        if not self.context.create() or not self.context.makeCurrent(self.surface): raise ViewerError('CLAP-RENDER-002','Не удалось создать OpenGL 2.1. Обновите драйвер видеокарты.')
        self.program=QOpenGLShaderProgram()
        vertex='attribute vec3 position; attribute vec3 normal; uniform mat4 mvp; uniform mat4 rotation; varying vec3 N; void main(){ gl_Position=mvp*vec4(position,1.0); N=(rotation*vec4(normal,0.0)).xyz; }'
        fragment='varying vec3 N; void main(){ vec3 n=normalize(N); float light=0.35+0.65*abs(dot(n,normalize(vec3(-0.4,0.7,1.0)))); gl_FragColor=vec4(vec3(0.62)*light,1.0); }'
        if not self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,vertex) or not self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment,fragment) or not self.program.link(): raise ViewerError('CLAP-RENDER-003',self.program.log())
        data=vertices if isinstance(vertices,bytes) else vertices.tobytes()
        if scene and self.materials:
            if len(scene.material_ids)*72!=len(data) or len(scene.coordinates)*2!=len(data): raise ValueError('Некорректные material ranges / coordinates')
            # Group opaque triangles once so each used material is drawn in one call.
            order=sorted(range(len(scene.material_ids)),key=scene.material_ids.__getitem__)
            data=b''.join(data[i*72:(i+1)*72] for i in order)
            coordinates=b''.join(scene.coordinates[i*36:(i+1)*36] for i in order)
            for i,triangle in enumerate(order):
                material=scene.material_ids[triangle]
                if material<-1 or material>=len(self.materials): raise ValueError('Некорректный material ID')
                if self.groups and self.groups[-1][0]==material:
                    key,start,count=self.groups[-1]; self.groups[-1]=(key,start,count+3)
                else: self.groups.append((material,i*3,3))
            self.coordinate_buffer=QOpenGLBuffer(); self.coordinate_buffer.create(); self.coordinate_buffer.bind(); self.coordinate_buffer.allocate(coordinates,len(coordinates)); self.coordinate_buffer.release()
        self.buffer=QOpenGLBuffer(); self.buffer.create(); self.buffer.bind(); self.buffer.allocate(data,len(data)); self.buffer.release()
        self.count=len(data)//24; self.fbo=None
        self.context.doneCurrent()

    def set_display_mode(self,mode):
        if mode not in self.allowed_modes: raise ValueError('Неизвестный режим отображения')
        if mode!='solid' and not self.materials: raise ValueError('В модели нет поддерживаемых материалов')
        if mode!='solid' and not self.material_programs:
            from PySide6.QtOpenGL import QOpenGLShaderProgram,QOpenGLShader
            from PySide6.QtOpenGL import QOpenGLTexture
            from PySide6.QtGui import QImage
            if not self.context.makeCurrent(self.surface): raise ViewerError('CLAP-RENDER-002','Потерян контекст')
            programs=[]; textures={}; uploaded={}
            try:
                for index,material in enumerate(self.materials):
                    program=QOpenGLShaderProgram(); programs.append(program)
                    vertex,fragment=self.material_source(material)
                    if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,vertex) or not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment,fragment) or not program.link():
                        raise ViewerError('CLAP-RENDER-003',program.log())
                    raster=material.texture
                    if raster is not None:
                        key=id(raster)
                        if key not in uploaded:
                            image=QImage(raster.pixels,raster.width,raster.height,raster.width*4,QImage.Format.Format_RGBA8888)
                            texture=QOpenGLTexture(image,QOpenGLTexture.MipMapGeneration.DontGenerateMipMaps)
                            uploaded[key]=texture
                            if not texture.isCreated():
                                raise ViewerError('CLAP-RENDER-003','Не удалось загрузить текстуру модели')
                            texture.setMinMagFilters(QOpenGLTexture.Filter.Linear,QOpenGLTexture.Filter.Linear)
                            texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
                        textures[index]=uploaded[key]
                self.material_programs=programs
                self.textures=textures
            except BaseException:
                for texture in uploaded.values(): texture.destroy()
                for program in programs: program.removeAllShaders()
                raise
            finally: self.context.doneCurrent()
        self.display_mode=mode

    def render(self,size,yaw,pitch,zoom):
        from PySide6.QtGui import QMatrix4x4
        from PySide6.QtOpenGL import QOpenGLFramebufferObject,QOpenGLFramebufferObjectFormat
        if not self.context.makeCurrent(self.surface): raise ViewerError('CLAP-RENDER-002','Потерян графический контекст')
        if self.fbo is None or self.fbo.size()!=size:
            self.fbo=None
            fmt=QOpenGLFramebufferObjectFormat(); fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil); fmt.setSamples(4)
            self.fbo=QOpenGLFramebufferObject(size,fmt)
        if not self.fbo.isValid(): raise ViewerError('CLAP-RENDER-003','Не удалось создать прозрачный framebuffer')
        self.fbo.bind(); gl=self.context.functions(); gl.glViewport(0,0,size.width(),size.height()); gl.glEnable(0x0B71); gl.glClearColor(0,0,0,0); gl.glClear(0x4000|0x0100)
        rotation=QMatrix4x4(); rotation.rotate(pitch,1,0,0); rotation.rotate(yaw,0,1,0)
        projection=QMatrix4x4(); projection.perspective(40,size.width()/size.height(),.1,100)
        view=QMatrix4x4(); view.translate(0,0,-3.5); view.scale(zoom)
        groups=self.groups if self.display_mode!='solid' else [(-1,0,self.count)]
        for material,start,count in groups:
            program=self.material_programs[material] if material>=0 else self.program
            program.bind(); program.setUniformValue('mvp',projection*view*rotation); program.setUniformValue('rotation',rotation)
            if program.uniformLocation('modelZoom')>=0: program.setUniformValue(program.uniformLocation('modelZoom'),float(zoom))
            self.configure_program(program)
            texture=self.textures.get(material)
            if texture is not None:
                texture.bind(1)
                program.setUniformValue(program.uniformLocation('base_color_texture'),1)
            self.buffer.bind()
            for name,offset in [('position',0),('normal',12)]:
                program.enableAttributeArray(name); program.setAttributeBuffer(name,0x1406,offset,3,24)
            self.buffer.release()
            if material>=0:
                self.coordinate_buffer.bind(); program.enableAttributeArray('texcoord'); program.setAttributeBuffer('texcoord',0x1406,0,3,12); self.coordinate_buffer.release()
            gl.glDrawArrays(0x0004,start,count)
            if texture is not None: texture.release(1)
            program.release()
        image=self.fbo.toImage(); self.fbo.release(); self.context.doneCurrent()
        if image.isNull(): raise ViewerError('CLAP-RENDER-003','Пустой кадр OpenGL')
        return image

    def close(self):
        if getattr(self,'closed',False): return
        self.closed=True
        context=getattr(self,'context',None); surface=getattr(self,'surface',None)
        if context and surface and context.makeCurrent(surface):
            self.fbo=None
            if getattr(self,'buffer',None): self.buffer.destroy()
            if getattr(self,'coordinate_buffer',None): self.coordinate_buffer.destroy()
            for texture in set(self.textures.values()): texture.destroy()
            self.textures.clear()
            for program in getattr(self,'material_programs',[]): program.removeAllShaders()
            self.material_programs=[]
            if getattr(self,'program',None): self.program.removeAllShaders(); self.program=None
            self.context.doneCurrent()
        if surface: surface.destroy()
        self.context=None
        self.surface=None
