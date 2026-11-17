"""ART tile atlas and indexed-tile windows."""
from collections import OrderedDict
from hashlib import sha256
from os.path import normcase
from pathlib import Path
import time

from PySide6.QtCore import Qt, QRect, QSettings, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractScrollArea, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..core import ViewerError
from .contracts import Asset, AssetFailure, RasterData
from ..png import PngWindow

CELL_WIDTH = 112
CELL_HEIGHT = 104
PREVIEW_SIDE = 82
MAX_PALETTE_BYTES = 768


def _palette_colors(palette):
    if len(palette) != MAX_PALETTE_BYTES or max(palette, default=0) > 63:
        raise ValueError('Палитра должна содержать 256 цветов Build.')
    colors = []
    for index in range(256):
        offset = index * 3
        red, green, blue = palette[offset:offset + 3]
        color = QColor(round(red * 255 / 63), round(green * 255 / 63),
                       round(blue * 255 / 63), 0 if index == 255 else 255)
        colors.append(color.rgba())
    return colors


def _external_palette(path):
    with Path(path).open('rb') as stream:
        return _palette_colors(stream.read(MAX_PALETTE_BYTES))


def _indexed_image(tile, palette):
    if tile.width <= 0 or tile.height <= 0 or len(tile.pixels) != tile.width * tile.height:
        raise ViewerError('CLAP-RENDER-001', 'Повреждены пиксели тайла ART.')
    image = QImage(tile.pixels, tile.width, tile.height, tile.width,
                   QImage.Format.Format_Indexed8).copy()
    image.setColorTable(palette)
    return image


def _tile_by_id(data, tile_id):
    return data.frames.get(tile_id) or data.tiles.get(tile_id)


def _animation_enabled(tile):
    value = int(tile.picanm)
    frame_count = value & 0x3F
    animation_type = (value >> 6) & 0x3
    return frame_count > 0 and animation_type > 0


class ArtGrid(QAbstractScrollArea):
    def __init__(self, data, palette, on_open_tile, parent=None):
        super().__init__(parent)
        self.data, self.palette = data, palette
        self.on_open_tile = on_open_tile
        self.tile_ids = sorted(
            tile_id for tile_id, tile in data.tiles.items()
            if tile.width > 0 and tile.height > 0)
        self.columns = 1
        self.selected = None
        self.started = time.monotonic()
        self.pixmaps = OrderedDict()
        self.animated_tiles = frozenset(
            tile_id for tile_id in self.tile_ids
            if _animation_enabled(data.tiles[tile_id]))
        self.setMouseTracking(True)
        self.viewport().setAutoFillBackground(True)
        self.viewport().setStyleSheet('background: #34363a')
        self.verticalScrollBar().setSingleStep(CELL_HEIGHT // 3)
        self.visible_frames = {}
        self.update_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_geometry()

    def update_geometry(self):
        self.columns = max(1, self.viewport().width() // CELL_WIDTH)
        rows = (len(self.tile_ids) + self.columns - 1) // self.columns
        total_height = rows * CELL_HEIGHT
        self.verticalScrollBar().setRange(0, max(0, total_height - self.viewport().height()))
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.horizontalScrollBar().setRange(0, 0)
        self.viewport().update()

    def _frame_id(self, tile_id, ticks):
        try:
            return self.data.frame(tile_id, ticks)
        except (OSError, ValueError, ViewerError):
            return None

    def _pixmap(self, actual_id, size):
        key = (actual_id, size)
        cached = self.pixmaps.get(key)
        if cached is not None:
            self.pixmaps.move_to_end(key)
            return cached
        tile = _tile_by_id(self.data, actual_id)
        image = _indexed_image(tile, self.palette)
        image = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        pixmap = QPixmap.fromImage(image)
        self.pixmaps[key] = pixmap
        while len(self.pixmaps) > 256:
            self.pixmaps.popitem(last=False)
        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.fillRect(event.rect(), QColor('#34363a'))
        top = self.verticalScrollBar().value()
        dirty = event.rect()
        first_row = max(0, (top + dirty.top()) // CELL_HEIGHT)
        last_row = min((len(self.tile_ids) - 1) // self.columns,
                       (top + dirty.bottom()) // CELL_HEIGHT)
        elapsed_ticks = int((time.monotonic() - self.started) * 120)
        for row in range(first_row, last_row + 1):
            for column in range(self.columns):
                index = row * self.columns + column
                if index >= len(self.tile_ids):
                    break
                tile_id = self.tile_ids[index]
                cell = QRect(column * CELL_WIDTH, row * CELL_HEIGHT - top,
                             CELL_WIDTH, CELL_HEIGHT)
                painter.fillRect(cell.adjusted(3, 3, -3, -3), QColor('#45484d'))
                if tile_id == self.selected:
                    painter.setPen(QColor('#ffb4e6'))
                    painter.drawRect(cell.adjusted(2, 2, -2, -2))
                if not dirty.intersects(cell):
                    continue
                frame = tile_id
                if tile_id in self.animated_tiles:
                    frame = self._frame_id(tile_id, elapsed_ticks)
                    self.visible_frames[index] = frame
                missing = frame is None
                pixmap = self._pixmap(tile_id if missing else frame, PREVIEW_SIDE)
                x = cell.x() + (cell.width() - pixmap.width()) // 2
                y = cell.y() + 5 + (PREVIEW_SIDE - pixmap.height()) // 2
                painter.drawPixmap(x, y, pixmap)
                painter.setPen(QColor('#f1f2f3'))
                label = f'{tile_id} !' if missing else str(tile_id)
                painter.drawText(cell.adjusted(5, 0, -5, -3),
                                 Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                                 label)
        painter.end()

    def _tile_at(self, position):
        y = position.y() + self.verticalScrollBar().value()
        row, column = divmod(y, CELL_HEIGHT)[0], max(0, position.x() // CELL_WIDTH)
        index = row * self.columns + column
        return self.tile_ids[index] if 0 <= index < len(self.tile_ids) else None

    def mousePressEvent(self, event):
        tile_id = self._tile_at(event.position().toPoint())
        if tile_id is not None:
            self.selected = tile_id
            self.viewport().update()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        tile_id = self._tile_at(event.position().toPoint())
        if tile_id is not None:
            self.on_open_tile(tile_id)
        super().mouseDoubleClickEvent(event)

    def refresh_animation(self):
        if not self.isVisible():
            return
        top = self.verticalScrollBar().value()
        viewport = self.viewport().rect()
        ticks = int((time.monotonic() - self.started) * 120)
        for index, previous in tuple(self.visible_frames.items()):
            row, column = divmod(index, self.columns)
            cell = QRect(column * CELL_WIDTH, row * CELL_HEIGHT - top, CELL_WIDTH, CELL_HEIGHT)
            if not viewport.intersects(cell):
                del self.visible_frames[index]
            elif self._frame_id(self.tile_ids[index], ticks) != previous:
                self.viewport().update(cell)


class ArtTileWindow(PngWindow):
    """Use the established PNG presentation with nearest-neighbour scaling."""
    def __init__(self, path, data, tile_id, palette, *, screen=None):
        self.art_data, self.tile_id, self.palette = data, tile_id, palette
        self.elapsed = time.monotonic()
        self.current_tile_id = tile_id
        tile = data.tiles[tile_id]
        pixels = _indexed_image(tile, palette).convertToFormat(
            QImage.Format.Format_RGBA8888).constBits().tobytes()
        raster = RasterData(pixels, tile.width, tile.height, True)
        asset = Asset(raster, frozenset({'view.move', 'view.zoom'}), {
            'width': tile.width, 'height': tile.height, 'alpha': True,
        })
        super().__init__(path, asset, screen=screen)
        self.last_frame = None
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(16)
        self.animation_timer.timeout.connect(self.update_frame)
        if _animation_enabled(tile):
            self.animation_timer.start()
        self.update_frame(force=True)

    def initial_scale(self, area):
        return min(10.0, area.width() * 0.8 / self.image.width(),
                   area.height() * 0.8 / self.image.height())

    def rescale(self):
        if not hasattr(self, 'image'):
            return
        area = self.image.width() * self.image.height()
        self.scale = min(self.scale, (16_000_000 / max(1, area)) ** 0.5)
        self.resize(max(1, round(self.image.width() * self.scale)),
                    max(1, round(self.image.height() * self.scale)))
        self.clearMask()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(self.rect(), self.image, self.image.rect())

    def wheelEvent(self, event):
        old = self.scale
        steps = event.angleDelta().y() / 120
        self.scale = max(0.25, min(20, old * 1.25 ** steps))
        cursor = event.position().toPoint()
        anchor = self.pos() + cursor
        self.rescale()
        ratio = self.scale / old
        self.move(anchor - type(cursor)(round(cursor.x() * ratio), round(cursor.y() * ratio)))

    def _ticks(self):
        return int((time.monotonic() - self.elapsed) * 120)

    def update_frame(self, force=False):
        try:
            actual_id = self.art_data.frame(self.tile_id, self._ticks())
        except (OSError, ValueError, ViewerError):
            actual_id = None
        tile = _tile_by_id(self.art_data, actual_id) if actual_id is not None else None
        if not force and actual_id == self.last_frame:
            return
        self.last_frame = actual_id
        if tile is None:
            actual_id = self.tile_id
            tile = self.art_data.tiles[self.tile_id]
            self.setWindowTitle(f'{self.path.name} · тайл {self.tile_id} · кадр пропущен')
        elif actual_id == self.tile_id:
            self.setWindowTitle(f'{self.path.name} · тайл {self.tile_id} · {tile.width} × {tile.height}')
        else:
            self.setWindowTitle(f'{self.path.name} · кадр {actual_id}')
        self.current_tile_id = actual_id
        center = self.geometry().center()
        self.image = _indexed_image(tile, self.palette).convertToFormat(
            QImage.Format.Format_RGBA8888)
        self.rescale()
        if self.geometry().center() != center:
            self.move(center - self.rect().center())

    def create_context_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction('Экспортировать тайл в PNG…', self.export_png)
        menu.addAction('Закрыть', self.close)
        return menu

    def contextMenuEvent(self, event):
        self.create_context_menu().exec(event.globalPos())

    def export_png(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Экспорт тайла', f'tile-{self.current_tile_id}.png', 'PNG (*.png)')
        if filename:
            tile = _tile_by_id(self.art_data, self.current_tile_id)
            if tile is None or not _indexed_image(tile, self.palette).save(filename, 'PNG'):
                QMessageBox.warning(self, 'Экспорт тайла', 'Не удалось записать PNG.')

    def closeEvent(self, event):
        self.animation_timer.stop()
        super().closeEvent(event)


class ArtWindow(QMainWindow):
    """Scroll through an ART file and open individual tiles."""
    def __init__(self, path, asset):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.path = Path(path).resolve()
        self.asset = asset
        self.data = asset.data
        self.tile_windows = []
        self.closed = False
        self.loading = False
        self.settings = QSettings('CLAP', 'Visual Viewer')
        self.colors, self.palette_source = self._initial_palette()
        self.resize(980, 760)
        central = QWidget(self)
        self.content_layout = QVBoxLayout(central)
        self.path_label = QLabel()
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.content_layout.addWidget(self.path_label)

        controls = QHBoxLayout()
        self.previous = QPushButton('←')
        self.previous.setAccessibleName('Предыдущий ART')
        self.previous.clicked.connect(lambda: self._navigate(-1))
        self.next = QPushButton('→')
        self.next.setAccessibleName('Следующий ART')
        self.next.clicked.connect(lambda: self._navigate(1))
        controls.addWidget(self.previous)
        controls.addWidget(self.next)
        self.position_label = QLabel()
        self.position_label.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.position_label)
        self.palette_label = QLabel()
        self.palette_label.setTextFormat(Qt.TextFormat.PlainText)
        self.palette_label.setWordWrap(True)
        controls.addWidget(self.palette_label, 1)
        self.pick_palette = QPushButton('Выбрать палитру…')
        self.pick_palette.clicked.connect(self._change_palette)
        controls.addWidget(self.pick_palette)
        self.content_layout.addLayout(controls)

        self.grid = ArtGrid(self.data, self.colors, self.open_tile, central)
        self.content_layout.addWidget(self.grid, 1)
        self.setCentralWidget(central)
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(33)
        self.animation_timer.timeout.connect(lambda: self.grid.refresh_animation())
        self._update_heading()
        self._update_animation()

    @property
    def _entry(self):
        return self.data.entries[self.data.position]

    def _settings_key(self):
        archive = self._entry.entry_index is not None
        scope = self.path if archive else self.path.parent
        digest = sha256(normcase(str(scope)).encode('utf-8')).hexdigest()
        kind = 'archive' if archive else 'directory'
        return f'art/palette/{kind}/{digest}'

    def _initial_palette(self):
        if self.data.palette is not None:
            return _palette_colors(self.data.palette), self.data.palette_source
        reason = self.data.palette_issue
        stored = self.settings.value(self._settings_key(), '', str)
        if stored:
            try:
                return _external_palette(stored), stored
            except (OSError, ValueError):
                reason = f'{reason} Сохранённая палитра недоступна или повреждена.'.strip()
        selection = self._select_palette(reason)
        if selection is None:
            raise AssetFailure('cancelled', 'CLAP-RENDER-005',
                               'Для просмотра ART требуется палитра Build.')
        return selection

    def _select_palette(self, reason=''):
        title = f'Выберите палитру Build. {reason}' if reason else 'Выберите палитру Build'
        while True:
            path, _ = QFileDialog.getOpenFileName(
                self, title, str(self.path.parent), 'Палитра Build (*.dat *.pal)')
            if not path:
                return None
            try:
                selected = Path(path).resolve()
                colors = _external_palette(selected)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Ошибка палитры Build', str(exc))
                continue
            self.settings.setValue(self._settings_key(), str(selected))
            self.settings.sync()
            return colors, str(selected)

    def _change_palette(self):
        selection = self._select_palette()
        if selection is None:
            return
        self.colors, self.palette_source = selection
        self.grid.palette = self.colors
        self.grid.pixmaps.clear()
        self.grid.viewport().update()
        for window in self.tile_windows:
            window.palette = self.colors
            window.update_frame(force=True)
        self._update_heading()

    def _update_heading(self):
        name = self._entry.name
        self.setWindowTitle(f'KEDR — {name}')
        self.path_label.setText(str(self.path))
        self.position_label.setText(f'{name} · {self.data.position + 1} из {len(self.data.entries)}')
        self.palette_label.setText(f'Палитра · {self.palette_source}')
        self.previous.setEnabled(not self.loading and self.data.position > 0)
        self.next.setEnabled(not self.loading and self.data.position + 1 < len(self.data.entries))
        self.pick_palette.setEnabled(not self.loading)

    def _update_animation(self):
        if self.grid.animated_tiles:
            self.animation_timer.start()
        else:
            self.animation_timer.stop()

    def _navigate(self, offset):
        position = self.data.position + offset
        if self.closed or self.loading or not 0 <= position < len(self.data.entries):
            return
        from ..png import open_art_navigation
        self.loading = True
        self._update_heading()
        try:
            open_art_navigation(self.data.entries[position], self._navigation_done,
                                report_error=self._navigation_failed)
        except Exception as exc:
            self._navigation_failed(exc)

    def _navigation_done(self, asset):
        if self.closed:
            return
        for window in tuple(self.tile_windows):
            window.close()
        old_grid = self.grid
        self.asset = asset
        self.data = asset.data
        self.path = Path(self._entry.path).resolve()
        self.grid = ArtGrid(self.data, self.colors, self.open_tile, self.centralWidget())
        self.content_layout.replaceWidget(old_grid, self.grid)
        old_grid.hide()
        old_grid.deleteLater()
        self.loading = False
        self._update_heading()
        self._update_animation()

    def _navigation_failed(self, exc):
        if self.closed:
            return
        self.loading = False
        self._update_heading()
        if exc is not None and getattr(exc, 'status', None) != 'cancelled':
            QMessageBox.warning(self, 'Ошибка открытия ART', str(exc))

    def open_tile(self, tile_id):
        window = ArtTileWindow(self.path, self.data, tile_id, self.colors, screen=self.screen())
        self.tile_windows.append(window)
        window.destroyed.connect(lambda: self.tile_windows.remove(window)
                                 if window in self.tile_windows else None)
        window.show()

    def closeEvent(self, event):
        self.closed = True
        self.animation_timer.stop()
        for window in tuple(self.tile_windows):
            window.close()
        event.accept()
