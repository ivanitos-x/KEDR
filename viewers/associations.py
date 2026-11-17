"""Opt-in HKCU Open With registration; never writes UserChoice."""
from pathlib import Path
import sys

from .visual.bootstrap import build_registry
def applications(registry=None):
    registry=registry or build_registry()
    return {'CLAP.PNG':('png',list(registry.extensions('scene.decode')))}
APPS = applications()  # compatibility export for existing callers

def register(remove=False, prefer=False):
    import winreg
    root = Path(__file__).resolve().parents[1]
    python = root / '.venv/Scripts/pythonw.exe'
    if not python.exists(): raise RuntimeError('Сначала выполните setup.ps1')
    def put(path,name,value):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key: winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    def unput(path,name):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key,name)
        except FileNotFoundError: pass
    def delete(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
                children=[]
                while True:
                    try: children.append(winreg.EnumKey(key,len(children)))
                    except OSError: break
            for child in children: delete(path+'\\'+child)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
        except FileNotFoundError: pass
    for prog,(module,exts) in applications().items():
        appname = 'CLAP Document Viewer' if module=='document' else 'KEDR'
        launcher = root / (appname+'.exe')
        if not remove and not launcher.exists(): raise RuntimeError('Сначала выполните build-launchers.ps1')
        appkey = 'Software\\Classes\\Applications\\'+launcher.name
        legacy_appkey = 'Software\\Classes\\Applications\\CLAP PNG Viewer.exe'
        base='Software\\Classes\\'+prog
        for ext in exts:
            extension_key = 'Software\\Classes\\'+ext
            location='Software\\Classes\\'+ext+'\\OpenWithProgids'
            if remove:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,location,0,winreg.KEY_SET_VALUE) as key: winreg.DeleteValue(key,prog)
                except FileNotFoundError: pass
            else:
                put(location,prog,'')
                if prefer: put(extension_key,'',prog)
            if remove:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,extension_key,0,winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                        if winreg.QueryValueEx(key,'')[0] == prog: winreg.DeleteValue(key,'')
                except FileNotFoundError: pass
        capabilities='Software\\CLAP\\'+prog+'\\Capabilities'
        if module=='png':
            for ext in ('.png','.art'):
                unput('Software\\Classes\\'+ext+'\\OpenWithProgids',prog)
                unput(capabilities+'\\FileAssociations',ext)
                unput(appkey+'\\SupportedTypes',ext)
                unput(legacy_appkey+'\\SupportedTypes',ext)
        if remove:
            delete('Software\\CLAP\\'+prog)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Software\\RegisteredApplications',0,winreg.KEY_SET_VALUE) as key: winreg.DeleteValue(key,prog)
            except FileNotFoundError: pass
        else:
            put('Software\\RegisteredApplications',prog,capabilities)
            put(capabilities,'ApplicationName',appname)
            put(capabilities,'ApplicationDescription','Автономный просмотрщик CLAP')
            for ext in exts: put(capabilities+'\\FileAssociations',ext,prog)
        if remove:
            delete(base)
            delete(appkey)
            if module=='png': delete(legacy_appkey)
        else:
            command = f'"{launcher}" "%1"'
            put(base,'',appname)
            put(base,'FriendlyTypeName',appname)
            put(base+'\\Application','ApplicationName',appname)
            put(base+'\\DefaultIcon','',f'"{launcher}",0')
            put(base+'\\shell\\open\\command','',command)
            put(appkey,'FriendlyAppName',appname)
            put(appkey+'\\shell\\open\\command','',command)
            for ext in exts: put(appkey+'\\SupportedTypes',ext,'')
            if module=='png':
                put(legacy_appkey,'FriendlyAppName',appname)
                put(legacy_appkey+'\\shell\\open\\command','',command)
                put(legacy_appkey,'NoOpenWith','')
    import ctypes
    ctypes.windll.shell32.SHChangeNotify(0x08000000,0,None,None)

if __name__=='__main__': register('--remove' in sys.argv, '--prefer' in sys.argv)
