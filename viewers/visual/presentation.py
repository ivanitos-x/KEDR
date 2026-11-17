"""Own one renderer at a time; switches are transactional and registry-driven."""
class RendererSession:
    def __init__(self,data,registry):
        self.data,self.registry=data,registry
        self.mode='solid'; self.closed=False; self.environment=None
        self.last_request=None
        descriptor=registry.operation('visual.scene-renderer','solid')
        self.descriptor=descriptor; self.backend=descriptor.factory(data)
    def modes(self):
        modes=[]
        for descriptor in self.registry.entries.values():
            if descriptor.contract_id!='visual.scene-renderer' or self.registry.reason(descriptor.module_id): continue
            for mode in descriptor.modes:
                selected=self.registry.operation('visual.scene-renderer',mode.key)
                if selected.module_id==descriptor.module_id: modes.append((mode.key,mode.label,not mode.requires_materials or bool(self.data.materials)))
        return tuple(modes)
    def render(self,*args):
        frame=self.backend.render(*args); self.last_request=args; return frame
    def set_display_mode(self,mode):
        if self.closed: raise RuntimeError('Renderer session closed')
        descriptor=self.registry.operation('visual.scene-renderer',mode)
        if descriptor.module_id==self.descriptor.module_id:
            self.backend.set_display_mode(mode); self.mode=mode; return
        new=descriptor.factory(self.data)
        try:
            new.set_display_mode(mode)
            if self.environment is not None and hasattr(new,'set_environment'): new.set_environment(self.environment)
            if self.last_request is not None: new.render(*self.last_request)
        except BaseException:
            try: new.close()
            except Exception: pass
            raise
        old=self.backend; self.backend=new; self.descriptor=descriptor; self.mode=mode
        try: old.close()
        except Exception: pass
    def set_environment(self,data):
        if not self.supports_environment: raise ValueError('Выберите режим с поддержкой окружения')
        self.backend.set_environment(data); self.environment=data
    @property
    def supports_environment(self): return 'scene.environment' in self.descriptor.provides
    def close(self):
        if not self.closed: self.closed=True; self.backend.close()
