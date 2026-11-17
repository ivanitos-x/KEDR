from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
def run():
    if len(sys.argv)>1 and sys.argv[1]=='png': sys.argv.pop(1)
    from viewers.png import main
    return main()

if __name__=='__main__':
    def report_unhandled(kind,exc,tb):
        import ctypes
        from viewers.redaction import redact
        ctypes.windll.user32.MessageBoxW(None,'CLAP-VIEW-001: Ошибка просмотрщика.\n'+redact(str(exc)),'CLAP — ошибка',0x10)
    sys.excepthook=report_unhandled
    try: code=run()
    except Exception as exc:
        # This also works if Qt itself failed to import: pythonw has no console.
        import ctypes
        from viewers.redaction import redact
        ctypes.windll.user32.MessageBoxW(None,'CLAP-VIEW-001: Не удалось запустить просмотрщик.\n'+redact(str(exc))+'\nПроверьте зависимости через setup.ps1.','CLAP — ошибка запуска',0x10)
        code=1
    raise SystemExit(code)
