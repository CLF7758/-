# This file is part of Prism.
#
# Prism is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Prism is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Prism.  If not, see <https://www.gnu.org/licenses/>.

"""Classes for items that are added to the scene by the user (images,
text).
"""

from collections import defaultdict
from functools import cached_property
import logging
import os
import tempfile

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QUrl


def _configure_media_backend():
    """Pick a working QtMultimedia backend.

    Some PyQt6 wheels ship an ffmpeg backend plugin whose FFmpeg DLLs
    are missing, so the plugin fails to load. Fall back to the Windows
    Media Foundation backend in that case; without a backend
    QMediaPlayer cannot be created at all.
    """
    loader = QtCore.QPluginLoader(
        QtCore.QLibraryInfo.path(
            QtCore.QLibraryInfo.LibraryPath.PluginsPath)
        + '/multimedia/ffmpegmediaplugin.dll')
    if not loader.load():
        logging.getLogger(__name__).debug(
            'ffmpeg media backend unavailable, '
            'falling back to windows backend')
        os.environ['QT_MEDIA_BACKEND'] = 'windows'


_configure_media_backend()

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from prism import commands
from prism.config import PrismSettings
from prism.constants import COLORS
from prism.selection import SelectableMixin


logger = logging.getLogger(__name__)

# ── Color group definitions (11 groups) ─────────────────────────
COLOR_GROUPS = [
    {"id": "red",    "label": "红色", "color": "#d95c62"},
    {"id": "orange", "label": "橙色", "color": "#d99046"},
    {"id": "yellow", "label": "黄色", "color": "#d6bc48"},
    {"id": "green",  "label": "绿色", "color": "#65a873"},
    {"id": "cyan",   "label": "青色", "color": "#54aeb4"},
    {"id": "blue",   "label": "蓝色", "color": "#5d8fe8"},
    {"id": "purple", "label": "紫色", "color": "#9a7be6"},
    {"id": "pink",   "label": "粉色", "color": "#d579a5"},
    {"id": "black",  "label": "黑色", "color": "#232626"},
    {"id": "white",  "label": "白色", "color": "#dfe4e1"},
    {"id": "gray",   "label": "灰色", "color": "#828986"},
]


def _rgb_to_hsl(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6.0 if g < b else 0.0)
        elif mx == g:
            h = (b - r) / d + 2.0
        else:
            h = (r - g) / d + 4.0
        h *= 60.0
    return h, s, l


def _color_group_from_rgb(r, g, b):
    h, s, l = _rgb_to_hsl(r, g, b)
    # Black: very dark pixels
    if l < 0.12:
        return "black"
    if l < 0.22 and s < 0.25:
        return "black"
    # White: very bright, near-neutral
    if l > 0.88 and s < 0.15:
        return "white"
    # Gray: low saturation, mid brightness
    if s < 0.10:
        return "gray"
    if s < 0.18 and l > 0.30 and l < 0.75:
        return "gray"
    # Chromatic: classify by hue range
    if h < 20 or h >= 335:
        return "red"
    if h < 46:
        return "orange"
    if h < 75:
        return "yellow"
    if h < 165:
        return "green"
    if h < 200:
        return "cyan"
    if h < 260:
        return "blue"
    if h < 295:
        return "purple"
    return "pink"


item_registry = {}

VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv',
    '.m4v', '.3gp', '.ts',
}

VIDEO_EMBED_THRESHOLD_MB = 50


def register_item(cls):
    item_registry[cls.TYPE] = cls
    return cls


def sort_by_filename(items):
    """Order items by filename.

    Items with a filename (ordered by filename) first, then items
    without a filename but with a save_id follow (ordered by
    save_id), then remaining items in the order that they have
    been inserted into the scene.
    """

    items_by_filename = []
    items_by_save_id = []
    items_remaining = []

    for item in items:
        if getattr(item, 'filename', None):
            items_by_filename.append(item)
        elif getattr(item, 'save_id', None):
            items_by_save_id.append(item)
        else:
            items_remaining.append(item)

    items_by_filename.sort(key=lambda x: x.filename)
    items_by_save_id.sort(key=lambda x: x.save_id)
    return items_by_filename + items_by_save_id + items_remaining


class PrismItemMixin(SelectableMixin):
    """Base for all items added by the user."""

    def set_pos_center(self, pos):
        """Sets the position using the item's center as the origin point."""

        self.setPos(pos - self.center_scene_coords)

    def has_selection_outline(self):
        return self.isSelected()

    def has_selection_handles(self):
        return (self.isSelected()
                and self.scene()
                and self.scene().has_single_selection())

    def selection_action_items(self):
        """The items affected by selection actions like scaling and rotating.
        """
        return [self]

    def on_selected_change(self, value):
        if (value and self.scene()
                and not self.scene().has_selection()
                and not self.scene().active_mode is None):
            self.bring_to_front()

    # ── Metadata: categories, tags, notes ──────────────────────────────

    @property
    def categories(self):
        return self._categories

    @categories.setter
    def categories(self, value):
        self._categories = list(value) if value else []
        self._notify_metadata_changed()

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = list(value) if value else []
        self._notify_metadata_changed()

    @property
    def notes(self):
        return self._notes

    @notes.setter
    def notes(self, value):
        self._notes = value or ''
        self._notify_metadata_changed()

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value or ''
        self._notify_metadata_changed()

    def init_metadata(self):
        """Initialise metadata fields with empty defaults."""
        self._group_id = None
        self._group_note = ''
        if not hasattr(self, '_categories'):
            self._categories = []
        if not hasattr(self, '_tags'):
            self._tags = []
        if not hasattr(self, '_notes'):
            self._notes = ''
        if not hasattr(self, '_title'):
            self._title = ''

    def _notify_metadata_changed(self):
        if self.scene() and hasattr(self.scene(), 'metadata_changed'):
            self.scene().metadata_changed.emit()

    def get_metadata_save_data(self):
        return {'categories': list(self._categories),
                'tags': list(self._tags),
                'notes': self._notes,
                'title': self._title,
                'groupId': self._group_id,
                'groupNote': self._group_note}

    def load_metadata_from_data(self, data):
        self._group_id = data.get('groupId')
        self._group_note = data.get('groupNote', '')
        self._categories = list(data.get('categories', []))
        self._tags = list(data.get('tags', []))
        self._notes = data.get('notes', '')
        self._title = data.get('title', '')

    def update_from_data(self, **kwargs):
        self.save_id = kwargs.get('save_id', self.save_id)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))
        if kwargs.get('flip', 1) != self.flip():
            self.do_flip()
        data = kwargs.get('data', {})
        self.load_metadata_from_data(data)


@register_item
class PrismPixmapItem(PrismItemMixin, QtWidgets.QGraphicsPixmapItem):
    """Class for images added by the user."""

    TYPE = 'pixmap'
    CROP_HANDLE_SIZE = 15

    def __init__(self, image, filename=None, **kwargs):
        super().__init__(QtGui.QPixmap.fromImage(image))
        self.save_id = None
        self.filename = filename
        self.reset_crop()
        logger.debug(f'Initialized {self}')
        self.is_image = True
        self.crop_mode = False
        self.init_selectable()
        self.settings = PrismSettings()
        self.grayscale = False
        self.color_group = None
        self.dominant_color = None
        self.init_metadata()

    @classmethod
    def create_from_data(self, **kwargs):
        item = kwargs.pop('item')
        data = kwargs.pop('data', {})
        item.filename = item.filename or data.get('filename')
        if 'crop' in data:
            item.crop = QtCore.QRectF(*data['crop'])
        item.setOpacity(data.get('opacity', 1))
        item.grayscale = data.get('grayscale', False)
        item.color_group = data.get('colorGroup')
        item.dominant_color = data.get('dominantColor')
        return item

    def __str__(self):
        size = self.pixmap().size()
        return (f'Image "{self.filename}" {size.width()} x {size.height()}')

    @property
    def crop(self):
        return self._crop

    @crop.setter
    def crop(self, value):
        logger.debug(f'Setting crop for {self} to {value}')
        self.prepareGeometryChange()
        self._crop = value
        self.update()

    @property
    def grayscale(self):
        return self._grayscale

    @grayscale.setter
    def grayscale(self, value):
        logger.debug('Setting grayscale for {self} to {value}')
        self._grayscale = value
        if value is True:
            # Using the grayscale image format to convert to grayscale
            # loses an image's tranparency. So the straightworward
            # following method gives us an ugly black replacement:
            # img = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)

            # Instead, we will fill the background with the current
            # canvas colour, so the issue is only visible if the image
            # overlaps other images. The way we do it here only works
            # as long as the canvas colour is itself grayscale,
            # though.
            img = QtGui.QImage(
                self.pixmap().size(), QtGui.QImage.Format.Format_Grayscale8)
            img.fill(QtGui.QColor(*COLORS['Scene:Canvas']))
            painter = QtGui.QPainter(img)
            painter.drawPixmap(0, 0, self.pixmap())
            painter.end()
            self._grayscale_pixmap = QtGui.QPixmap.fromImage(img)

            # Alternative methods that have their own issues:
            #
            # 1. Use setAlphaChannel of the resulting grayscale
            # image. How do we get the original alpha channel? Using
            # the whole original image also takes color values into
            # account, not just their alpha values.
            #
            # 2. QtWidgets.QGraphicsColorizeEffect() with black colour
            # on the GraphicsItem. This applys to everything the paint
            # method does, so the selection outline/handles will also
            # be gray. setGraphicsEffect is only available on some
            # widgets, so we can't apply it selectively.
            #
            # 3. Going through every pixel and doing it manually — bad
            # performance.
        else:
            self._grayscale_pixmap = None

        self.update()

    def sample_color_at(self, pos):
        ipos = self.mapFromScene(pos)
        if self.grayscale:
            pm = self._grayscale_pixmap
        else:
            pm = self.pixmap()
        img = pm.toImage()

        color = img.pixelColor(int(ipos.x()), int(ipos.y()))
        if color.alpha():
            return color

    def bounding_rect_unselected(self):
        if self.crop_mode:
            return QtWidgets.QGraphicsPixmapItem.boundingRect(self)
        else:
            return self.crop

    def get_extra_save_data(self):
        data = {'filename': self.filename,
                'opacity': self.opacity(),
                'grayscale': self.grayscale,
                'crop': [self.crop.topLeft().x(),
                         self.crop.topLeft().y(),
                         self.crop.width(),
                         self.crop.height()]}
        if self.color_group:
            data['colorGroup'] = self.color_group
        if self.dominant_color:
            data['dominantColor'] = self.dominant_color
        data.update(self.get_metadata_save_data())
        return data

    def get_filename_for_export(self, imgformat, save_id_default=None):
        save_id = self.save_id or save_id_default
        assert save_id is not None

        if self.filename:
            basename = os.path.splitext(os.path.basename(self.filename))[0]
            return f'{save_id:04}-{basename}.{imgformat}'
        else:
            return f'{save_id:04}.{imgformat}'

    def get_imgformat(self, img):
        """Determines the format for storing this image."""

        formt = self.settings.valueOrDefault('Items/image_storage_format')

        if formt == 'best':
            # Images with alpha channel and small images are stored as png
            if (img.hasAlphaChannel()
                    or (img.height() < 500 and img.width() < 500)):
                formt = 'png'
            else:
                formt = 'jpg'

        logger.debug(f'Found format {formt} for {self}')
        return formt

    def pixmap_to_bytes(self, apply_grayscale=False, apply_crop=False):
        """Convert the pixmap data to PNG bytestring."""
        barray = QtCore.QByteArray()
        buffer = QtCore.QBuffer(barray)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if apply_grayscale and self.grayscale:
            pm = self._grayscale_pixmap
        else:
            pm = self.pixmap()

        if apply_crop:
            pm = pm.copy(self.crop.toRect())

        img = pm.toImage()
        imgformat = self.get_imgformat(img)
        img.save(buffer, imgformat.upper(), quality=90)
        return (barray.data(), imgformat)

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap)
        self.reset_crop()

    def pixmap_from_bytes(self, data):
        """Set image pimap from a bytestring."""
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        self.setPixmap(pixmap)

    def create_copy(self):
        item = PrismPixmapItem(QtGui.QImage(), self.filename)
        item.setPixmap(self.pixmap())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        item.setOpacity(self.opacity())
        item.grayscale = self.grayscale
        item.color_group = self.color_group
        item.dominant_color = self.dominant_color
        if self.flip() == -1:
            item.do_flip()
        item.crop = self.crop
        item._categories = list(self._categories)
        item._tags = list(self._tags)
        item._notes = self._notes
        item._title = getattr(self, '_title', '')
        return item

    @cached_property
    def color_gamut(self):
        logger.debug(f'Calculating color gamut for {self}')
        gamut = defaultdict(int)
        img = self.pixmap().toImage()
        # Don't evaluate every pixel for larger images:
        step = max(1, int(max(img.width(), img.height()) / 1000))
        logger.debug(f'Considering every {step}. row/column')

        # Not actually faster than solution below :(
        # ptr = img.bits()
        # size = img.sizeInBytes()
        # pixelsize = int(img.sizeInBytes() / img.width() / img.height())
        # ptr.setsize(size)
        # for pixel in batched(ptr, n=pixelsize):
        #     r, g, b, alpha = tuple(map(ord, pixel))
        #     if 5 < alpha and 5 < r < 250 and 5 < g < 250 and 5 < b < 250:
        #         # Only consider pixels that aren't close to
        #         # transparent, white or black
        #         rgb = QtGui.QColor(r, g, b)
        #         gamut[rgb.hue(), rgb.saturation()] += 1

        for i in range(0, img.width(), step):
            for j in range(0, img.height(), step):
                rgb = img.pixelColor(i, j)
                rgbtuple = (rgb.red(), rgb.blue(), rgb.green())
                if (5 < rgb.alpha()
                        and min(rgbtuple) < 250 and max(rgbtuple) > 5):
                    # Only consider pixels that aren't close to
                    # transparent, white or black
                    gamut[rgb.hue(), rgb.saturation()] += 1

        logger.debug(f'Got {len(gamut)} color gamut values')
        return gamut


    def analyze_color_group(self):
        """Analyse the image and assign self.color_group / self.dominant_color."""
        img = self.pixmap().toImage()
        max_side = 72
        w, h = img.width(), img.height()
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            img = img.scaled(
                max(1, int(w * scale)), max(1, int(h * scale)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation)
        gw = defaultdict(float)
        gr = defaultdict(float)
        gg = defaultdict(float)
        gb = defaultdict(float)
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() < 180:
                    continue
                r, g, b = c.red(), c.green(), c.blue()
                gid = _color_group_from_rgb(r, g, b)
                _, sv, _ = _rgb_to_hsl(r, g, b)
                wt = 1.0
                if gid in ('black', 'white', 'gray'):
                    wt *= 0.72
                if sv > 0.5:
                    wt *= 1.9
                gw[gid] += wt
                gr[gid] += r * wt
                gg[gid] += g * wt
                gb[gid] += b * wt
        if not gw:
            self.color_group = 'gray'
            self.dominant_color = '#828986'
            return
        best = max(gw, key=gw.get)
        self.color_group = best
        ws = gw[best]
        self.dominant_color = f'#{int(gr[best]/ws):02x}{int(gg[best]/ws):02x}{int(gb[best]/ws):02x}'

    def copy_to_clipboard(self, clipboard):
        clipboard.setPixmap(self.pixmap())

    def reset_crop(self):
        self.crop = QtCore.QRectF(
            0, 0, self.pixmap().size().width(), self.pixmap().size().height())

    @property
    def crop_handle_size(self):
        return self.fixed_length_for_viewport(self.CROP_HANDLE_SIZE)

    def crop_handle_topleft(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomleft(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x(),
            bottomleft.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomright(self):
        bottomright = self.crop_temp.bottomRight()
        return QtCore.QRectF(
            bottomright.x() - self.crop_handle_size,
            bottomright.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_topright(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handles(self):
        return (self.crop_handle_topleft,
                self.crop_handle_bottomleft,
                self.crop_handle_bottomright,
                self.crop_handle_topright)

    def crop_edge_top(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x() + self.crop_handle_size,
            topleft.y(),
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_left(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edge_bottom(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x() + self.crop_handle_size,
            bottomleft.y() - self.crop_handle_size,
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_right(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edges(self):
        return (self.crop_edge_top,
                self.crop_edge_left,
                self.crop_edge_bottom,
                self.crop_edge_right)

    def get_crop_handle_cursor(self, handle):
        """Gets the crop cursor for the given handle."""

        is_topleft_or_bottomright = handle in (
            self.crop_handle_topleft, self.crop_handle_bottomright)
        return self.get_diag_cursor(is_topleft_or_bottomright)

    def get_crop_edge_cursor(self, edge):
        """Gets the crop edge cursor for the given edge."""

        top_or_bottom = edge in (
            self.crop_edge_top, self.crop_edge_bottom)
        sideways = (45 < self.rotation() < 135
                    or 225 < self.rotation() < 315)

        if top_or_bottom is sideways:
            return Qt.CursorShape.SizeHorCursor
        else:
            return Qt.CursorShape.SizeVerCursor

    def draw_crop_rect(self, painter, rect):
        """Paint a dotted rectangle for the cropping UI."""
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect)
        pen.setColor(QtGui.QColor(0, 0, 0))
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def paint(self, painter, option, widget):
        if abs(painter.combinedTransform().m11()) < 2:
            # We want image smoothing, but only for images where we
            # are not zoomed in a lot. This is to ensure that for
            # example icons and pixel sprites can be viewed correctly.
            painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)

        if self.crop_mode:
            self.paint_debug(painter, option, widget)

            # Darken image outside of cropped area
            painter.drawPixmap(0, 0, self.pixmap())
            path = QtWidgets.QGraphicsPixmapItem.shape(self)
            path.addRect(self.crop_temp)
            color = QtGui.QColor(0, 0, 0)
            color.setAlpha(100)
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            painter.setBrush(QtGui.QBrush())

            for handle in self.crop_handles():
                self.draw_crop_rect(painter, handle())
            self.draw_crop_rect(painter, self.crop_temp)
        else:
            pm = self._grayscale_pixmap if self.grayscale else self.pixmap()
            painter.drawPixmap(self.crop, pm, self.crop)
            self.paint_selectable(painter, option, widget)

    def enter_crop_mode(self):
        logger.debug(f'Entering crop mode on {self}')
        self.prepareGeometryChange()
        self.crop_mode = True
        self.crop_temp = QtCore.QRectF(self.crop)
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.grabKeyboard()
        self.update()
        self.scene().crop_item = self

    def exit_crop_mode(self, confirm):
        logger.debug(f'Exiting crop mode with {confirm} on {self}')
        if confirm and self.crop != self.crop_temp:
            self.scene().undo_stack.push(
                commands.CropItem(self, self.crop_temp))
        self.prepareGeometryChange()
        self.crop_mode = False
        self.crop_temp = None
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.ungrabKeyboard()
        self.update()
        self.scene().crop_item = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.exit_crop_mode(confirm=True)
        elif event.key() == Qt.Key.Key_Escape:
            self.exit_crop_mode(confirm=False)
        else:
            super().keyPressEvent(event)

    def hoverMoveEvent(self, event):
        if not self.crop_mode:
            return super().hoverMoveEvent(event)

        for handle in self.crop_handles():
            if handle().contains(event.pos()):
                self.set_cursor(self.get_crop_handle_cursor(handle))
                return
        for edge in self.crop_edges():
            if edge().contains(event.pos()):
                self.set_cursor(self.get_crop_edge_cursor(edge))
                return
        self.unset_cursor()

    def mousePressEvent(self, event):
        if not self.crop_mode:
            return super().mousePressEvent(event)

        event.accept()
        for handle in self.crop_handles():
            # Click into a handle?
            if handle().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = handle
                return
        for edge in self.crop_edges():
            # Click into an edge handle?
            if edge().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = edge
                return
        # Click not in handle, end cropping mode:
        self.exit_crop_mode(
            confirm=self.crop_temp.contains(event.pos()))

    def ensure_point_within_crop_bounds(self, point, handle):
        """Returns the point, or the nearest point within the pixmap."""

        if handle == self.crop_handle_topleft:
            topleft = QtCore.QPointF(0, 0)
            bottomright = self.crop_temp.bottomRight()
        if handle == self.crop_handle_bottomleft:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_handle_bottomright:
            topleft = self.crop_temp.topLeft()
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_handle_topright:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_top:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_bottom:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_edge_left:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_edge_right:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())

        point.setX(min(bottomright.x(), max(topleft.x(), point.x())))
        point.setY(min(bottomright.y(), max(topleft.y(), point.y())))

        return point

    def mouseMoveEvent(self, event):
        if self.crop_mode and self.crop_mode_event_start:
            diff = event.pos() - self.crop_mode_event_start
            if self.crop_mode_move == self.crop_handle_topleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTopLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottomLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomRight() + diff, self.crop_mode_move)
                self.crop_temp.setBottomRight(new)
            if self.crop_mode_move == self.crop_handle_topright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setTopRight(new)
            if self.crop_mode_move == self.crop_edge_top:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTop(new.y())
            if self.crop_mode_move == self.crop_edge_left:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setLeft(new.x())
            if self.crop_mode_move == self.crop_edge_bottom:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottom(new.y())
            if self.crop_mode_move == self.crop_edge_right:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setRight(new.x())
            self.update()
            self.crop_mode_event_start = event.pos()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.crop_mode:
            self.crop_mode_move = None
            self.crop_mode_event_start = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


@register_item
class PrismTextItem(PrismItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for text added by the user."""

    TYPE = 'text'

    def __init__(self, text=None, **kwargs):
        super().__init__(text or "Text")
        self.save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = True
        self.edit_mode = False
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))
        self.init_metadata()

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Text "{txt}"')

    def get_extra_save_data(self):
        data = {'text': self.toPlainText()}
        data.update(self.get_metadata_save_data())
        return data

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QtGui.QColor(0, 0, 0)
        color.setAlpha(40)
        brush = QtGui.QBrush(color)
        painter.setBrush(brush)
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self))
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    def create_copy(self):
        item = PrismTextItem(self.toPlainText())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        item._categories = list(self._categories)
        item._tags = list(self._tags)
        item._notes = self._notes
        item._title = getattr(self, '_title', '')
        return item

    def enter_edit_mode(self):
        logger.debug(f'Entering edit mode on {self}')
        self.edit_mode = True
        self.old_text = self.toPlainText()
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.scene().edit_item = self

    def exit_edit_mode(self, commit=True):
        logger.debug(f'Exiting edit mode on {self}')
        self.edit_mode = False
        # reset selection:
        self.setTextCursor(QtGui.QTextCursor(self.document()))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.scene().edit_item = None
        if commit:
            self.scene().undo_stack.push(
                commands.ChangeText(self, self.toPlainText(), self.old_text))
            if not self.toPlainText().strip():
                logger.debug('Removing empty text item')
                self.scene().undo_stack.push(
                    commands.DeleteItems(self.scene(), [self]))
        else:
            self.setPlainText(self.old_text)

    def has_selection_handles(self):
        return super().has_selection_handles() and not self.edit_mode

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode()
            event.accept()
            return
        if (event.key() == Qt.Key.Key_Escape
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode(commit=False)
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_to_clipboard(self, clipboard):
        clipboard.setText(self.toPlainText())


@register_item
class PrismErrorItem(PrismItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for displaying error messages when an item can't be loaded
    from a bee file.

    This item will be displayed instead of the original item. It won't
    save to bee files. The original item will be preserved in the bee
    file, unless this item gets deleted by the user, or a new bee file
    is saved.
    """

    TYPE = 'error'

    def __init__(self, text=None, **kwargs):
        super().__init__(text or "Text")
        self.original_save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = False
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))
        self.init_metadata()

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Error "{txt}"')

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QtGui.QColor(200, 0, 0)
        brush = QtGui.QBrush(color)
        painter.setBrush(brush)
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self))
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    def update_from_data(self, **kwargs):
        self.original_save_id = kwargs.get('save_id', self.original_save_id)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))

    def create_copy(self):
        item = PrismErrorItem(self.toPlainText())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        return item

    def flip(self, *args, **kwargs):
        """Returns the flip value (1 or -1)"""
        # Never display error messages flipped
        return 1

    def do_flip(self, *args, **kwargs):
        """Flips the item."""
        # Never flip error messages
        pass

    def copy_to_clipboard(self, clipboard):
        clipboard.setText(self.toPlainText())


@register_item
class PrismVideoItem(PrismItemMixin, QtWidgets.QGraphicsPixmapItem):
    """Class for video items added by the user.

    Displays a thumbnail (first frame or placeholder) when not playing.
    When playing, updates the pixmap from QMediaPlayer video frames.
    """

    TYPE = 'video'

    def __init__(self, video_url=None, filename=None, video_blob=None):
        """Create a video item.

        :param video_url: QUrl pointing to the video file on disk
        :param filename: Original filename for display/save purposes
        :param video_blob: Raw video bytes (for embedded storage)
        """
        super().__init__()
        self.save_id = None
        self.filename = filename
        self.is_image = False
        self.is_editable = False
        self.init_selectable()

        self._video_url = video_url
        self._video_blob = video_blob
        self._is_reference = False
        self._playing = False
        self._loop = False
        self._muted = False
        self._player = None
        self._player_source = None
        self._audio_output = None
        self._video_sink = None
        self._tmp_video_file = None
        self._control_bar = None
        self._thumb_player = None
        self._thumb_audio = None
        self._thumb_sink = None
        self._current_frame = None

        self._generate_placeholder()
        # Thumbnail capture deferred to itemChange(ItemSceneHasChanged)
        # to ensure the Qt event loop is running and media backend is ready

        if filename:
            logger.debug(f'Initialized {self}')

    def _generate_placeholder(self):
        """Create a placeholder thumbnail with a play icon."""
        w, h = 640, 360
        pm = QtGui.QPixmap(w, h)
        pm.fill(QtGui.QColor(50, 50, 50))
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setBrush(QtGui.QColor(200, 200, 200, 180))
        p.setPen(Qt.PenStyle.NoPen)
        cx, cy = w // 2, h // 2
        r = 35
        p.drawEllipse(QtCore.QPointF(cx, cy), r, r)
        p.setBrush(QtGui.QColor(50, 50, 50))
        tri = QtGui.QPolygonF([
            QtCore.QPointF(cx - 10, cy - 18),
            QtCore.QPointF(cx - 10, cy + 18),
            QtCore.QPointF(cx + 18, cy),
        ])
        p.drawPolygon(tri)
        p.end()
        self.setPixmap(pm)

    def _capture_thumbnail(self):
        """Asynchronously capture the first frame as thumbnail.

        Uses a temporary QMediaPlayer with an explicit QVideoSink.
        The first valid frame that the sink delivers becomes the
        thumbnail; the temp player is torn down right after.
        """
        player = QMediaPlayer()
        audio = QAudioOutput()
        audio.setMuted(True)
        audio.setVolume(0)
        sink = QVideoSink()
        player.setAudioOutput(audio)
        player.setVideoOutput(sink)
        player.setSource(self._video_url)

        state = {'done': False}

        def teardown():
            for signal, slot in (
                    (player.mediaStatusChanged, on_media_status),
                    (player.errorOccurred, on_error),
                    (sink.videoFrameChanged, on_video_frame)):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            player.deleteLater()
            sink.deleteLater()
            audio.deleteLater()
            # Drop our references so later cleanup() won't touch the
            # deleted C++ objects.
            if self._thumb_player is player:
                self._thumb_player = None
            if self._thumb_audio is audio:
                self._thumb_audio = None
            if self._thumb_sink is sink:
                self._thumb_sink = None

        def on_video_frame(frame):
            if state['done']:
                return
            if frame.isValid():
                state['done'] = True
                img = frame.toImage()
                if not img.isNull():
                    self.setPixmap(QtGui.QPixmap.fromImage(img))
                    if self._control_bar:
                        self._control_bar.reposition()
                    self.update()
                player.stop()
                teardown()

        def on_error(error, error_string):
            logger.debug(f'Thumbnail capture error: '
                         f'{error} {error_string}')
            state['done'] = True
            teardown()

        def on_media_status(status):
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                # No usable frame was delivered; give up quietly and
                # keep the placeholder.
                state['done'] = True
                teardown()

        sink.videoFrameChanged.connect(on_video_frame)
        player.mediaStatusChanged.connect(on_media_status)
        player.errorOccurred.connect(on_error)
        player.play()
        self._thumb_player = player
        self._thumb_audio = audio
        self._thumb_sink = sink

    @classmethod
    def create_from_data(cls, **kwargs):
        item = kwargs.pop('item')
        data = kwargs.pop('data', {})
        item.filename = item.filename or data.get('filename')
        item.setOpacity(data.get('opacity', 1))
        if 'loop' in data:
            item._loop = data['loop']
        if 'mute' in data:
            item._muted = data['mute']
        if 'isReference' in data:
            item._is_reference = data['isReference']
        if data.get('videoPath'):
            path = data['videoPath']
            if os.path.exists(path):
                item._video_url = QUrl.fromLocalFile(path)
                item._capture_thumbnail()
            else:
                logger.warning(f'Video file missing: {path}')
        return item

    def __str__(self):
        return f'Video "{self.filename}"'

    def get_extra_save_data(self):
        data = {
            'filename': self.filename,
            'opacity': self.opacity(),
            'loop': self._loop,
            'mute': self._muted,
            'isReference': self._is_reference,
        }
        if self._is_reference and self._video_url:
            path = self._video_url.toLocalFile()
            if path:
                data['videoPath'] = os.path.abspath(path)
        return data

    def get_filename_for_export(self, imgformat, save_id_default=None):
        save_id = self.save_id or save_id_default
        assert save_id is not None
        if self.filename:
            basename = os.path.splitext(
                os.path.basename(self.filename))[0]
            ext = os.path.splitext(self.filename)[1] or '.mp4'
            return f'{save_id:04}-{basename}{ext}'
        return f'{save_id:04}.mp4'

    # ── Playback ─────────────────────────────────────────────

    def play(self):
        """Start or resume video playback."""
        if not self._video_url:
            return
        path = self._video_url.toLocalFile()
        if not os.path.exists(path):
            logger.warning(f'Video file not found: {path}')
            return

        if self._video_blob and not self._tmp_video_file:
            ext = os.path.splitext(path)[1] or '.mp4'
            self._tmp_video_file = tempfile.NamedTemporaryFile(
                suffix=ext, delete=False)
            self._tmp_video_file.write(self._video_blob)
            self._tmp_video_file.close()
            self._player_source = QUrl.fromLocalFile(
                self._tmp_video_file.name)
        else:
            self._player_source = self._video_url

        if self._player is None:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._video_sink = QVideoSink()
            self._player.setAudioOutput(self._audio_output)
            self._player.setVideoOutput(self._video_sink)
            self._audio_output.setMuted(self._muted)
            self._player.setLoops(
                QMediaPlayer.Loops.Infinite
                if self._loop
                else QMediaPlayer.Loops.Once)
            self._player.setSource(self._player_source)
            self._video_sink.videoFrameChanged.connect(
                self._on_video_frame)
            self._player.mediaStatusChanged.connect(
                self._on_media_status)

        self._player.play()
        self._playing = True
        if self._control_bar:
            self._control_bar.show()
            self._control_bar.update_state(True)
        self.update()

    def pause(self):
        """Pause video playback."""
        if self._player:
            self._player.pause()
        self._playing = False
        if self._control_bar:
            self._control_bar.update_state(False)
        self.update()

    def toggle_play(self):
        """Toggle between play and pause."""
        if self._playing:
            self.pause()
        else:
            if (self._player
                    and self._player.position()
                    >= self._player.duration()):
                self._player.setPosition(0)
            self.play()

    def set_muted(self, muted):
        self._muted = muted
        if self._audio_output:
            self._audio_output.setMuted(muted)

    def set_loop(self, loop):
        self._loop = loop
        if self._player:
            self._player.setLoops(
                QMediaPlayer.Loops.Infinite
                if loop
                else QMediaPlayer.Loops.Once)

    def seek(self, position_ms):
        if self._player:
            self._player.setPosition(position_ms)

    def position(self):
        if self._player:
            return self._player.position()
        return 0

    def duration(self):
        if self._player:
            return self._player.duration()
        return 0

    # ── Internal slots ───────────────────────────────────────

    def _on_video_frame(self, frame):
        if frame.isValid():
            img = frame.toImage()
            if not img.isNull():
                self._current_frame = QtGui.QPixmap.fromImage(img)
                self.update()

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if not self._loop:
                self._playing = False
                if self._control_bar:
                    self._control_bar.update_state(False)
                self.update()

    # ── Painting ─────────────────────────────────────────────

    def paint(self, painter, option, widget):
        if abs(painter.combinedTransform().m11()) < 2:
            painter.setRenderHint(
                painter.RenderHint.SmoothPixmapTransform)

        if self._playing and self._current_frame:
            painter.drawPixmap(
                self.boundingRect().toRect(),
                self._current_frame,
                self._current_frame.rect())
        else:
            painter.drawPixmap(
                self.boundingRect().toRect(),
                self.pixmap(),
                self.pixmap().rect())

            # Centered play button overlay (YouTube-style)
            rect = self.boundingRect()
            cx = rect.center().x()
            cy = rect.center().y()
            radius = min(rect.width(), rect.height()) * 0.12
            radius = max(radius, 18)

            # Semi-transparent dark circle background
            painter.setBrush(QtGui.QColor(0, 0, 0, 140))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)

            # White play triangle
            tri_r = radius * 0.45
            offset_x = tri_r * 0.2  # slight right offset for optical center
            triangle = QtGui.QPolygonF([
                QtCore.QPointF(cx - tri_r + offset_x, cy - tri_r),
                QtCore.QPointF(cx - tri_r + offset_x, cy + tri_r),
                QtCore.QPointF(cx + tri_r + offset_x, cy),
            ])
            painter.setBrush(QtGui.QColor(255, 255, 255, 220))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(triangle)

        # Never draw selection outline on video items
        option.state &= ~QtWidgets.QStyle.StateFlag.State_Selected


    def has_selection_outline(self):
        return False
    # ── Copy / clipboard ─────────────────────────────────────

    def create_copy(self):
        item = PrismVideoItem(self._video_url, self.filename,
                            self._video_blob)
        item._is_reference = self._is_reference
        item._loop = self._loop
        item._muted = self._muted
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        item.setOpacity(self.opacity())
        if self.flip() == -1:
            item.do_flip()
        return item

    def copy_to_clipboard(self, clipboard):
        if self.filename:
            clipboard.setText(self.filename)

    # ── Cleanup ──────────────────────────────────────────────

    def cleanup(self):
        """Stop playback and remove temporary files."""
        if self._player:
            self._player.stop()
            try:
                self._player.mediaStatusChanged.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._player = None
            self._audio_output = None
        if self._video_sink:
            try:
                self._video_sink.videoFrameChanged.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._video_sink = None
        if self._thumb_player:
            self._thumb_player.stop()
            try:
                self._thumb_player.mediaStatusChanged.disconnect()
                self._thumb_player.positionChanged.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._thumb_player = None
            self._thumb_audio = None
        if self._thumb_sink:
            try:
                self._thumb_sink.videoFrameChanged.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._thumb_sink = None
        if self._tmp_video_file:
            try:
                os.unlink(self._tmp_video_file.name)
            except OSError:
                pass
            self._tmp_video_file = None
        if self._control_bar:
            self._control_bar.hide()

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Force scene to repaint old area to avoid ghosting
            if self._playing and self.scene():
                self.scene().update(self.sceneBoundingRect())
        elif change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSceneChange:
            if self._playing:
                self.cleanup()
            if value is None and self._control_bar:
                # Item leaves the scene; drop the control bar with it
                self._control_bar.hide()
                self._control_bar.deleteLater()
                self._control_bar = None
        elif (change
              == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged):
            if self.scene() and self._control_bar is None:
                from prism.widgets.video_controls import (
                    PrismVideoControlProxy)
                self._control_bar = PrismVideoControlProxy(self)
            # Capture thumbnail now that item is in scene and event loop is active
            if self._video_url and self.pixmap().size() == QtCore.QSize(640, 360):
                QtCore.QTimer.singleShot(100, self._capture_thumbnail)
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        super().hoverEnterEvent(event)
        if self._control_bar and self._playing:
            self._control_bar.show()

    def hoverLeaveEvent(self, event):
        super().hoverLeaveEvent(event)
        if self._control_bar and not self._playing:
            self._control_bar.hide()
