"""Deterministic catalog. It grants no privileges and runs no code from documents."""
from .contracts import AssetFailure

class Registry:
    def __init__(self, grants=frozenset({'file.read.selected'})):
        self.entries = {}
        self.grants = grants
    def register(self, descriptor):
        if descriptor.module_id in self.entries: raise ValueError('Duplicate module_id: '+descriptor.module_id)
        if descriptor.api_version != '1.0' or descriptor.contract_id not in {'visual.asset-loader','visual.scene-renderer','visual.mesh-modifier','visual.environment-loader','visual.asset-window'}: raise ValueError('Incompatible visual contract')
        if any(mode.key not in descriptor.accepts for mode in descriptor.modes): raise ValueError('Mode is not declared in accepts')
        if not descriptor.permissions <= self.grants: raise ValueError('Module requests permissions outside host policy')
        self.entries[descriptor.module_id] = descriptor
    def validate(self):
        def visit(key, path):
            if key in path: raise ValueError('Module dependency cycle')
            if key not in self.entries: raise ValueError('Missing module dependency: '+key)
            for dep in self.entries[key].requires: visit(dep,path|{key})
        for key in self.entries: visit(key,set())
    def reason(self, key):
        d=self.entries[key]
        if d.unavailable: return d.unavailable
        for dependency in d.requires:
            reason=self.reason(dependency)
            if reason: return reason
        return ''
    def extensions(self):
        return tuple(sorted({ext for d in self.entries.values() if d.contract_id=='visual.asset-loader' and not self.reason(d.module_id) for ext in d.accepts}))
    def operation(self,contract,key):
        matches=[d for d in self.entries.values() if d.contract_id==contract and key in d.accepts and not self.reason(d.module_id)]
        if not matches: raise AssetFailure('unavailable','CLAP-RENDER-006','Нет обработчика операции '+key)
        priority=max(d.priority for d in matches); matches=[d for d in matches if d.priority==priority]
        if len(matches)!=1: raise AssetFailure('blocked','CLAP-RENDER-005','Неоднозначная операция '+key)
        return matches[0]
    def resolve(self, suffix, header):
        matches=[d for d in self.entries.values() if d.contract_id=='visual.asset-loader' and suffix in d.accepts]
        if not matches: raise AssetFailure('unsupported','CLAP-RENDER-005','Неподдерживаемый формат')
        available=[d for d in matches if not self.reason(d.module_id)]
        if not available: raise AssetFailure('unavailable','CLAP-RENDER-006', '; '.join(self.reason(d.module_id) for d in matches))
        priority=max(d.priority for d in available)
        candidates=[d for d in available if d.priority==priority]
        if len(candidates)!=1: raise AssetFailure('blocked','CLAP-RENDER-005','Неоднозначный обработчик формата')
        loader=candidates[0].factory()
        if not loader.probe(header): raise AssetFailure('invalid_input','CLAP-RENDER-001','Сигнатура файла не соответствует расширению')
        return candidates[0],loader
