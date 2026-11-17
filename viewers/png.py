"""Per-pixel translucent independent PNG windows, with native alpha hit testing."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QPoint, QThread, Signal
from PySide6.QtGui import QCursor, QImageReader, QPainter, QRegion, QBitmap
from PySide6.QtWidgets import QApplication, QWidget, QFileDialog, QMenu, QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton
from .core import ViewerError
from .dialogs import error

from .visual.formats.glb import load_glb
from .visual.renderers.solid_gl import SolidRenderer

class PngWindow(QWidget):
    def __init__(self, path, asset=None, *, screen=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.path = Path(path).resolve()
        from .visual.bootstrap import open_asset,create_presentation
        self.asset = asset or open_asset(self.path)
        self.capabilities = self.asset.capabilities
        self.is_model = 'view.rotate' in self.capabilities  # compatibility property, derived from capabilities
        self.renderer = None
        self.yaw = self.pitch = 0.0
        self.zoom = 1.0
        self.model_info = self.asset.info
        self.image,self.renderer = create_presentation(self.asset)
        self.scale = 1.0
        self.press = None
        self.press_button = Qt.MouseButton.NoButton
        self.activating_click = False
        self.dragged = False
        self.topmost = False
        self.auto_rotation = False
        self.menu_open = False
        self.display_mode = self.renderer.mode if self.renderer is not None else 'solid'
        self.setWindowTitle(self.path.name)
        self._reset_on_screen(screen or QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen())

    def reset(self):
        self._reset_on_screen(self.screen())

    def _reset_on_screen(self, screen):
        if self.is_model:
            self.yaw=self.pitch=0.0; self.zoom=1.0
            self.refresh_model()
        area = screen.availableGeometry()
        self.scale = self.initial_scale(area)
        self.rescale()
        self.move(area.center()-self.rect().center())

    def initial_scale(self, area):
        return min(1.0,area.width()*.85/self.image.width(),area.height()*.85/self.image.height())

    def rescale(self):
        self.resize(max(1,round(self.image.width()*self.scale)),max(1,round(self.image.height()*self.scale)))
        # A binary input region excludes fully transparent pixels while paint retains all alpha levels.
        scaled = self.image.scaled(self.size(),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        if self.image.hasAlphaChannel():
            from PySide6.QtGui import QImage
            alpha = scaled.convertToFormat(QImage.Format.Format_Alpha8)
            # Translate alpha 1..255 to 255 for input only; visual alpha is untouched.
            raw = bytes(alpha.constBits()).translate(bytes([0]+[255]*255))
            solid = QImage(raw,alpha.width(),alpha.height(),alpha.bytesPerLine(),QImage.Format.Format_Alpha8).convertToFormat(QImage.Format.Format_ARGB32)
            self.setMask(QRegion(QBitmap.fromImage(solid.createAlphaMask())))
        else: self.clearMask()
        self.update()

    def paintEvent(self,event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(),self.image)

    def wheelEvent(self,event):
        if self.is_model:
            self.zoom=max(.1,min(1.5,self.zoom*(1.1 if event.angleDelta().y()>0 else 1/1.1)))
            self.refresh_model()
            return
        old = self.scale
        new = max(.02,min(8.0,old*(1.15 if event.angleDelta().y()>0 else 1/1.15)))
        if self.image.width()*self.image.height()*new*new > 16_000_000: return
        cursor = event.position().toPoint()
        anchor = self.pos()+cursor
        self.scale = new
        self.rescale()
        self.move(anchor-QPoint(round(cursor.x()*new/old),round(cursor.y()*new/old)))

    def nativeEvent(self,event_type,message):
        if sys.platform=='win32' and event_type==b'windows_generic_MSG':
            from ctypes.wintypes import MSG
            native=MSG.from_address(int(message))
            # Windows activates the window before Qt delivers the mouse press.
            if native.message==0x0021:  # WM_MOUSEACTIVATE
                self.activating_click=((native.lParam >> 16) & 0xffff)==0x0201  # WM_LBUTTONDOWN
        return super().nativeEvent(event_type,message)

    def mousePressEvent(self,event):
        button=event.button()
        if self.press is None and button in (Qt.MouseButton.LeftButton,Qt.MouseButton.MiddleButton):
            was_inactive=self.activating_click or not self.isActiveWindow()
            self.activating_click=False
            if was_inactive:
                self.raise_()
                self.activateWindow()
            self.press_button=button
            self.close_on_release=button==Qt.MouseButton.LeftButton and not was_inactive
            self.press = event.globalPosition().toPoint()
            self.origin = self.pos()
            self.dragged = False
            self.start_angles=(self.yaw,self.pitch)
            self.moving=button==Qt.MouseButton.MiddleButton or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

    def mouseMoveEvent(self,event):
        if self.press is not None:
            delta = event.globalPosition().toPoint()-self.press
            if delta.manhattanLength() >= QApplication.startDragDistance(): self.dragged = True
            if self.dragged:
                if self.is_model and not self.moving:
                    self.yaw=self.start_angles[0]+delta.x()*.5
                    self.pitch=self.start_angles[1]+delta.y()*.5
                    self.schedule_model()
                else: self.move(self.origin+delta)

    def mouseReleaseEvent(self,event):
        if event.button()==self.press_button and self.press is not None:
            self.press = None
            self.press_button=Qt.MouseButton.NoButton
            if self.close_on_release and not self.dragged: self.close()

    def create_context_menu(self):
        menu = QMenu(self)
        menu.addAction('Открыть другой файл…',open_files)
        if self.is_model:
            modes=menu.addMenu('Режим отображения')
            menu._mode_menu=modes  # retain the Python wrapper while the popup lives
            for key,label,enabled in self.renderer.modes():
                action=modes.addAction(label)
                action.setCheckable(True); action.setChecked(self.display_mode==key); action.setEnabled(enabled)
                action.triggered.connect(lambda _,selected=key: self.set_display_mode(selected))
            if 'view.palette' in self.capabilities:
                menu.addAction('Загрузить палитру Build…',self.choose_palette)
                if hasattr(self,'embedded_palette_asset'):
                    menu.addAction('Вернуть палитру KVX',self.restore_palette)
            environment=menu.addAction('Освещение PBR → открыть HDRI…',self.open_environment)
            environment.setEnabled(self.renderer.supports_environment)
            studio=menu.addAction('Освещение PBR → встроенная студия',lambda:self.set_environment(None))
            studio.setEnabled(self.renderer.supports_environment)
            auto = menu.addAction('Автоматическое вращение вокруг вертикальной оси')
            auto.setCheckable(True)
            auto.setChecked(self.auto_rotation)
            auto.triggered.connect(self.toggle_auto_rotation)
            menu.addAction('Сбросить вращение',self.reset_rotation)
            menu.addAction('Сбросить положение',self.reset_position)
            menu.addAction('Сбросить масштаб',self.reset_zoom)
            menu.addAction('Восстановить исходный вид',self.reset)
        else: menu.addAction('Сбросить масштаб / положение',self.reset)
        action = menu.addAction('Поверх всех окон')
        action.setCheckable(True)
        action.setChecked(self.topmost)
        action.triggered.connect(self.toggle_top)
        if self.is_model:
            info=self.model_info
            menu.addAction('Сведения о модели',lambda: QMessageBox.information(self,info.get('format','Модель'),f"{self.path}\nВершин (с экземплярами): {info.get('evaluated_vertices',info['vertices'])}\nВершин исходного меша: {info['vertices']}\nТреугольников: {info['triangles']}\nОбъектов: {info['objects']}\nБайт: {info['bytes']}\nСтатическая сцена; режим: {self.display_mode}\n"+'\n'.join(self.asset.notices)))
        else: menu.addAction('Сведения о файле',lambda: QMessageBox.information(self,'PNG',f'{self.path}\n{self.image.width()} × {self.image.height()}\nАльфа-канал: {self.image.hasAlphaChannel()}\nМасштаб: {self.scale:.0%}'))
        menu.addAction('Закрыть',self.close)
        menu._owned_actions=menu.actions()
        if self.is_model: modes._owned_actions=modes.actions()
        return menu

    def contextMenuEvent(self,event):
        menu=self.create_context_menu()
        self.menu_open=True
        try: menu.exec(event.globalPos())
        finally: self.menu_open=False

    def toggle_auto_rotation(self,enabled):
        import time
        from PySide6.QtCore import QTimer
        self.auto_rotation=bool(enabled) and 'view.rotate' in self.capabilities
        if not hasattr(self,'auto_timer'):
            self.auto_timer=QTimer(self)
            self.auto_timer.setInterval(33)
            self.auto_timer.timeout.connect(self.auto_rotate_tick)
        self.auto_last=time.monotonic()
        if self.auto_rotation and self.isVisible(): self.auto_timer.start()
        else: self.auto_timer.stop()

    def auto_rotate_tick(self):
        import time
        now=time.monotonic(); elapsed=min(.1,now-self.auto_last); self.auto_last=now
        if self.auto_rotation and self.renderer and self.press is None and not self.menu_open and not self.isMinimized():
            self.yaw=(self.yaw+elapsed*20)%360
            self.refresh_model()

    def hideEvent(self,event):
        if hasattr(self,'auto_timer'): self.auto_timer.stop()
        super().hideEvent(event)

    def showEvent(self,event):
        super().showEvent(event)
        if getattr(self,'auto_rotation',False): self.toggle_auto_rotation(True)

    def toggle_top(self,value):
        self.topmost = value
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,value)
        self.show()

    def set_display_mode(self,mode):
        try:
            self.renderer.set_display_mode(mode)
            self.display_mode=mode
            self.refresh_model()
        except Exception as exc: error(self,exc)

    def open_environment(self):
        path,_=QFileDialog.getOpenFileName(self,'Окружение PBR','','Radiance HDR (*.hdr)')
        if path:
            from .visual.bootstrap import load_environment
            LoadingDialog(path,operation=load_environment,callback=self.set_environment)

    def choose_palette(self):
        path,_=QFileDialog.getOpenFileName(self,'Палитра Build',str(self.path.parent),'Палитра Build (*.dat *.pal)')
        if path:
            try: self.apply_palette(path)
            except Exception as exc: error(self,exc)

    def apply_palette(self,path):
        from .visual.palette import replace_palette
        original=getattr(self,'embedded_palette_asset',self.asset)
        self.update_palette(replace_palette(original,path))
        self.embedded_palette_asset=original

    def restore_palette(self):
        try:
            self.update_palette(self.embedded_palette_asset)
            del self.embedded_palette_asset
        except Exception as exc: error(self,exc)

    def update_palette(self,asset):
        from .visual.presentation import RendererSession
        old=self.renderer
        candidate=RendererSession(asset.data,old.registry)
        try:
            candidate.set_display_mode('materials' if old.mode=='solid' else old.mode)
            if candidate.supports_environment and old.environment is not None:
                candidate.set_environment(old.environment)
            frame=candidate.render(self.image.size(),self.yaw,self.pitch,self.zoom)
        except BaseException:
            candidate.close()
            raise
        self.asset,self.renderer,self.image=asset,candidate,frame
        self.display_mode=candidate.mode
        old.close()
        self.rescale()

    def set_environment(self,data):
        if self.renderer is None: return
        try: self.renderer.set_environment(data); self.refresh_model()
        except Exception as exc: error(self,exc)

    def schedule_model(self):
        from PySide6.QtCore import QTimer
        if not hasattr(self,'render_timer'):
            self.render_timer=QTimer(self); self.render_timer.setSingleShot(True)
            self.render_timer.timeout.connect(self.refresh_model)
        if not self.render_timer.isActive(): self.render_timer.start(16)

    def refresh_model(self):
        try:
            self.image=self.renderer.render(self.image.size(),self.yaw,self.pitch,self.zoom)
            self.rescale()
        except Exception as exc:
            self.toggle_auto_rotation(False)
            error(self,exc if isinstance(exc,ViewerError) else ViewerError('CLAP-RENDER-003',exc,file=self.path))

    def reset_rotation(self):
        self.yaw=self.pitch=0.0; self.refresh_model()

    def reset_zoom(self):
        self.zoom=1.0; self.refresh_model()

    def reset_position(self):
        screen=self.screen().availableGeometry(); self.move(screen.center()-self.rect().center())

    def closeEvent(self,event):
        if hasattr(self,'auto_timer'): self.auto_timer.stop()
        if hasattr(self,'render_timer'): self.render_timer.stop()
        if self.renderer:
            self.renderer.close(); self.renderer=None
        event.accept()

windows = []
pending_loads = set()

class AssetWorker(QThread):
    ready=Signal(object)
    failed=Signal(object)
    progress=Signal(str)
    def __init__(self,path,context,operation=None):
        super().__init__(); self.path,self.context,self.operation=path,context,operation
    def run(self):
        from .visual.bootstrap import open_asset
        try: self.ready.emit((self.operation or open_asset)(Path(self.path),self.context))
        except Exception as exc: self.failed.emit(exc)

class LoadingDialog(QDialog):
    def __init__(self,path,operation=None,callback=None,palette=None,report_error=None):
        super().__init__()
        from .visual.contracts import LoadContext
        self.setWindowTitle('KEDR — загрузка')
        self.context=LoadContext(palette_path=Path(palette) if palette else None); self.done_loading=False
        self.result_asset=None; self.failure=None; self.path=path; self.callback=callback
        self.report_error=report_error
        layout=QVBoxLayout(self); self.label=QLabel('Открытие '+Path(path).name); layout.addWidget(self.label)
        button=QPushButton('Отмена'); button.clicked.connect(self.cancel); layout.addWidget(button)
        self.worker=AssetWorker(path,self.context,operation)
        self.context.progress=self.worker.progress.emit
        self.worker.progress.connect(self.label.setText)
        self.worker.ready.connect(lambda asset: self.loaded(path,asset))
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finish)
        pending_loads.add(self); self.show(); self.worker.start()
    def cancel(self):
        self.context.cancel.set(); self.label.setText('Отмена загрузки…')
    def closeEvent(self,event):
        if self.done_loading: event.accept()
        else: self.cancel(); event.ignore()
    def loaded(self,path,asset):
        self.result_asset=asset
    def failed(self,exc):
        self.failure=exc
    def notify_failure(self,exc):
        if self.report_error is not None: self.report_error(exc)
        elif getattr(exc,'status',None)!='cancelled': error(self,exc)
    def finish(self):
        # Do not enter a modal error loop while finished is still queued: that
        # signal used to delete the loading dialog and its child error box.
        self.done_loading=True
        self.worker.deleteLater()
        try:
            if self.context.cancel.is_set():
                from .visual.contracts import AssetFailure
                self.notify_failure(AssetFailure('cancelled','CLAP-RENDER-007','Открытие отменено'))
            else:
                if self.failure is not None:
                    self.notify_failure(self.failure)
                elif self.result_asset is not None:
                    try:
                        if self.callback: self.callback(self.result_asset)
                        else: show_asset(self.path,self.result_asset)
                    except Exception as exc:
                        self.notify_failure(exc)
        finally:
            pending_loads.discard(self); self.close(); self.deleteLater()

def show_asset(path,asset,mode=None,palette=None):
    from .visual.bootstrap import create_asset_window
    window=create_asset_window(path,asset)
    if window is None:
        window=PngWindow(path,asset)
        if palette:
            try: window.apply_palette(palette)
            except BaseException:
                window.close()
                raise
        if mode: window.set_display_mode(mode)
    windows.append(window)
    window.destroyed.connect(lambda: windows.remove(window) if window in windows else None)
    window.show()

def open_path(path,mode=None,palette=None):
    LoadingDialog(path,callback=(lambda asset:show_asset(path,asset,mode,palette)) if mode or palette else None,
                  palette=palette)

def open_art_navigation(entry,callback,palette=None,report_error=None):
    return open_art_entry(entry.path,entry.entry_index,callback,palette,report_error)

def open_art_entry(path,entry_index,callback=None,palette=None,report_error=None):
    from .visual.bootstrap import open_art_archive
    operation=None
    if entry_index is not None:
        operation=lambda selected,context: open_art_archive(selected,entry_index,context)
    return LoadingDialog(path,operation=operation,callback=callback,palette=palette,
                         report_error=report_error)

def open_files(mode=None):
    from .visual.bootstrap import file_filter
    paths,_ = QFileDialog.getOpenFileNames(None,'KEDR','',file_filter())
    for path in paths: open_path(path,mode if isinstance(mode,str) else None)

def main():
    import argparse
    from .visual.bootstrap import build_registry
    app = QApplication(sys.argv)
    registry=build_registry()
    choices=[mode.key for d in registry.entries.values() if d.contract_id=='visual.scene-renderer' and not registry.reason(d.module_id) for mode in d.modes]
    class Arguments(argparse.ArgumentParser):
        def error(self,message): raise ValueError('Некорректные аргументы: '+message)
    parser=Arguments(prog='KEDR')
    parser.add_argument('--wait',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--mode',choices=choices)
    parser.add_argument('--palette',help='Палитра Build для ART или KVX')
    parser.add_argument('--grp',type=Path,help='Архив Build GRP')
    parser.add_argument('--entry-index',type=int,help='Индекс записи ART в каталоге GRP, начиная с нуля')
    parser.add_argument('files',nargs='*')
    args=parser.parse_args(sys.argv[1:])
    if (args.grp is None)!=(args.entry_index is None):
        parser.error('Укажите --grp и --entry-index вместе')
    if args.grp is not None:
        if args.files or args.mode:
            parser.error('Для --grp укажите индекс записи ART и, при необходимости, --palette')
        if args.entry_index<0:
            parser.error('Индекс записи GRP должен быть неотрицательным')
        open_art_entry(args.grp,args.entry_index,palette=args.palette)
    elif args.files:
        for path in args.files: open_path(path,args.mode,args.palette)
    else:
        if args.palette: parser.error('Укажите файл ART или KVX для палитры')
        open_files(args.mode)
    if not windows and not pending_loads: return 0
    return app.exec()

if __name__=='__main__': sys.exit(main())
