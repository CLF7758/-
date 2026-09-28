"""Right sidebar inspector panel (PureRef style).

Shows preview, title, notes, category, file info,
color distribution and histogram for selected item."""

import logging
import os
from datetime import datetime

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from prism import commands
from prism.config import PrismSettings
from prism.items import (PrismPixmapItem, PrismVideoItem, COLOR_GROUPS,
                               _color_group_from_rgb, _rgb_to_hsl)


logger = logging.getLogger(__name__)


def _format_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


class DetailPanel(QtWidgets.QWidget):
    """Right sidebar inspector panel."""

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.scene = view.scene
        self._item = None
        self._setup_ui()
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.scene.metadata_changed.connect(self._refresh)

    def _setup_ui(self):
        self.setStyleSheet(
            'QWidget { background-color: #1c1c1e; }'
            'QLabel { color: #e5e5e7; }'
        )
        self.setMinimumWidth(260)
        self.setMaximumWidth(16777215)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(6)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            'QScrollArea { border: none; background: transparent; }')
        outer.addWidget(scroll, stretch=1)

        body = QtWidgets.QWidget()
        self._body_layout = QtWidgets.QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(12)
        scroll.setWidget(body)

        # Preview thumbnail
        self._preview_label = QtWidgets.QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setFixedHeight(150)
        self._preview_label.setStyleSheet(
            'background: rgba(28,28,30,0.8); border-radius: 6px;')
        self._body_layout.addWidget(self._preview_label)

        # Title
        lbl_title = QtWidgets.QLabel('\u6807\u9898')
        lbl_title.setStyleSheet(
            'font-weight: 600; '
            'color: rgba(245,245,247,0.72);')
        self._body_layout.addWidget(lbl_title)
        self._title_edit = QtWidgets.QLineEdit()
        self._title_edit.setStyleSheet(
            'QLineEdit { background: rgba(58,58,60,0.6); '
            '  border: 1px solid rgba(255,255,255,0.04); '
            '  border-radius: 4px; color: #e5e5e7; '
            '  padding: 3px 6px; }')
        self._title_edit.editingFinished.connect(
            lambda: self._on_title_changed(self._title_edit.text()))
        self._body_layout.addWidget(self._title_edit)

        # Notes
        lbl_notes = QtWidgets.QLabel('\u5907\u6ce8')
        lbl_notes.setStyleSheet(
            'font-weight: 600; '
            'color: rgba(245,245,247,0.72);')
        self._body_layout.addWidget(lbl_notes)
        self._notes_edit = QtWidgets.QTextEdit()
        self._notes_edit.setPlaceholderText('\u6dfb\u52a0\u5907\u6ce8\u2026')
        self._notes_edit.setFixedHeight(100)
        self._notes_edit.setStyleSheet(
            'QTextEdit { background: rgba(58,58,60,0.6); '
            '  border: 1px solid rgba(255,255,255,0.04); '
            '  border-radius: 4px; color: #e5e5e7; '
            '  padding: 3px; }')
        self._notes_edit.textChanged.connect(self._on_notes_changed)
        self._body_layout.addWidget(self._notes_edit)

        # Category dropdown
        lbl_cat = QtWidgets.QLabel('\u5206\u7c7b')
        lbl_cat.setStyleSheet(
            'font-weight: 600; '
            'color: rgba(245,245,247,0.72);')
        self._body_layout.addWidget(lbl_cat)
        self._cat_combo = QtWidgets.QComboBox()
        self._cat_combo.setStyleSheet(
            'QComboBox { background: rgba(58,58,60,0.6); '
            '  border: 1px solid rgba(255,255,255,0.04); '
            '  border-radius: 4px; color: #e5e5e7; '
            '  padding: 3px 6px; }'
            'QComboBox::drop-down { border: none; }'
            'QComboBox QAbstractItemView { '
            '  background: #3a3a3c; color: #e5e5e7; '
            '  selection-background-color: rgba(10,132,255,0.3); }')
        self._cat_combo.currentIndexChanged.connect(
            self._on_category_changed)
        self._body_layout.addWidget(self._cat_combo)

        # Info grid
        grid_style = 'color: rgba(245,245,247,0.72);'
        val_style = 'color: #e5e5e7;'

        self._info_grid = QtWidgets.QFormLayout()
        self._info_grid.setContentsMargins(0, 2, 0, 0)
        self._info_grid.setSpacing(3)
        self._info_grid.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._type_label = QtWidgets.QLabel()
        self._type_label.setStyleSheet(val_style)
        t1 = QtWidgets.QLabel('\u7c7b\u578b')
        t1.setStyleSheet(grid_style)
        self._info_grid.addRow(t1, self._type_label)

        self._dims_label = QtWidgets.QLabel()
        self._dims_label.setStyleSheet(val_style)
        t2 = QtWidgets.QLabel('\u5c3a\u5bf8')
        t2.setStyleSheet(grid_style)
        self._info_grid.addRow(t2, self._dims_label)

        self._size_label = QtWidgets.QLabel()
        self._size_label.setStyleSheet(val_style)
        t3 = QtWidgets.QLabel('\u6587\u4ef6\u5927\u5c0f')
        t3.setStyleSheet(grid_style)
        self._info_grid.addRow(t3, self._size_label)

        self._date_label = QtWidgets.QLabel()
        self._date_label.setStyleSheet(val_style)
        t4 = QtWidgets.QLabel('\u65f6\u95f4')
        t4.setStyleSheet(grid_style)
        self._info_grid.addRow(t4, self._date_label)

        self._path_label = QtWidgets.QLabel()
        self._path_label.setStyleSheet(val_style)
        self._path_label.setWordWrap(True)
        t5 = QtWidgets.QLabel('\u8def\u5f84')
        t5.setStyleSheet(grid_style)
        self._info_grid.addRow(t5, self._path_label)

        self._body_layout.addLayout(self._info_grid)

        # Color distribution
        lbl_cd = QtWidgets.QLabel('颜色分布')
        lbl_cd.setStyleSheet(
            'font-weight: 600; '
            'color: rgba(245,245,247,0.72); padding-top: 2px;')
        self._body_layout.addWidget(lbl_cd)
        self._cd_container = QtWidgets.QWidget()
        self._cd_layout = QtWidgets.QVBoxLayout(self._cd_container)
        self._cd_layout.setContentsMargins(0, 0, 0, 0)
        self._cd_layout.setSpacing(2)
        self._body_layout.addWidget(self._cd_container)

        # Histogram
        lbl_hist = QtWidgets.QLabel('直方图')
        lbl_hist.setStyleSheet(
            'font-weight: 600; '
            'color: rgba(245,245,247,0.72); padding-top: 4px;')
        self._body_layout.addWidget(lbl_hist)
        self._hist_widget = _HistogramWidget()
        self._hist_widget.setMinimumHeight(180)
        self._hist_widget.setStyleSheet(
            'background: rgba(28,28,30,0.8); border-radius: 4px;')
        self._body_layout.addWidget(self._hist_widget)

        self._body_layout.addStretch()

        self._show_empty()

    # ── Public API ──────────────────────────────────────────────

    def _show_empty(self):
        self._item = None
        self._preview_label.setText('\u672a\u9009\u4e2d\u7d20\u6750')
        self._title_edit.setEnabled(False)
        self._title_edit.clear()
        self._notes_edit.setEnabled(False)
        self._notes_edit.blockSignals(True)
        self._notes_edit.clear()
        self._notes_edit.blockSignals(False)
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        self._cat_combo.blockSignals(False)
        self._type_label.setText('\u2014')
        self._dims_label.setText('\u2014')
        self._size_label.setText('\u2014')
        self._date_label.setText('\u2014')
        self._path_label.setText('\u2014')
        self._hist_widget.clear()

    def _on_selection_changed(self):
        selected = self.scene.selectedItems(user_only=True)
        if len(selected) != 1:
            self._show_empty()
            if selected:
                self._preview_label.setText(f'已选中 {len(selected)} 个素材')
                self._cat_combo.blockSignals(True)
                self._cat_combo.addItem('选择分类以批量移动…', None)
                self._cat_combo.addItem('未分类', [])
                for name in self._load_categories():
                    self._cat_combo.addItem(name, [name])
                self._cat_combo.blockSignals(False)
            return
        self._refresh_item(selected[0])

    def _refresh(self):
        if self._item:
            self._refresh_item(self._item)

    def _refresh_item(self, item):
        self._item = item

        # Preview
        pm = getattr(item, 'pixmap', lambda: None)()
        if pm and not pm.isNull():
            scaled = pm.scaled(
                max(200, self.width() - 40), 145,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._preview_label.setPixmap(scaled)
        else:
            txt = '\u89c6\u9891' if isinstance(item, PrismVideoItem) else '\u65e0\u9884\u89c8'
            self._preview_label.setText(txt)

        # Title
        title = getattr(item, '_title', None) or getattr(
            item, 'filename', '\u672a\u547d\u540d')
        self._title_edit.setEnabled(True)
        self._title_edit.blockSignals(True)
        self._title_edit.setText(title)
        self._title_edit.blockSignals(False)

        # Notes
        notes = getattr(item, '_notes', '')
        self._notes_edit.setEnabled(True)
        self._notes_edit.blockSignals(True)
        self._notes_edit.setPlainText(notes)
        self._notes_edit.blockSignals(False)

        # Category dropdown
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        self._cat_combo.addItem('\u672a\u5206\u7c7b', [])
        cats = self._load_categories()
        for c in sorted(cats):
            self._cat_combo.addItem(c, [c])
        item_cats = getattr(item, '_categories', [])
        if len(item_cats) > 1:
            self._cat_combo.addItem('、'.join(item_cats), list(item_cats))
            self._cat_combo.setCurrentIndex(self._cat_combo.count() - 1)
        elif item_cats:
            idx = self._cat_combo.findText(item_cats[0])
            if idx >= 0:
                self._cat_combo.setCurrentIndex(idx)
        self._cat_combo.blockSignals(False)

        # Info grid
        if isinstance(item, PrismPixmapItem):
            self._type_label.setText('\u56fe\u7247')
            if pm and not pm.isNull():
                self._dims_label.setText(
                    f'{pm.width()} \u00d7 {pm.height()}')
            else:
                self._dims_label.setText('\u672a\u77e5')
        elif isinstance(item, PrismVideoItem):
            self._type_label.setText('\u89c6\u9891')
            if pm and not pm.isNull():
                self._dims_label.setText(
                    f'{pm.width()} \u00d7 {pm.height()}')
            else:
                self._dims_label.setText('\u672a\u77e5')
        else:
            self._type_label.setText('\u672a\u77e5')
            self._dims_label.setText('\u2014')

        # File size and path
        url = getattr(item, '_video_url', None)
        fn = getattr(item, 'filename', None)
        fpath = None
        if url and hasattr(url, 'toLocalFile'):
            fpath = url.toLocalFile()
        elif fn and os.path.isabs(fn):
            fpath = fn
        if fpath and os.path.exists(fpath):
            try:
                stat = os.stat(fpath)
                self._size_label.setText(_format_bytes(stat.st_size))
                mtime = datetime.fromtimestamp(stat.st_mtime)
                self._date_label.setText(mtime.strftime('%Y-%m-%d %H:%M'))
            except OSError:
                self._size_label.setText('\u672a\u77e5')
                self._date_label.setText('\u672a\u77e5')
            self._path_label.setText(fpath)
            self._path_label.setToolTip(fpath)
        else:
            self._size_label.setText('\u672a\u77e5')
            self._date_label.setText('\u672a\u77e5')
            self._path_label.setText(fn or '\u672a\u77e5')

        # Color distribution (only for images)
        if isinstance(item, PrismPixmapItem):
            self._build_color_distribution(item)
        else:
            while hasattr(self, '_cd_layout') and self._cd_layout.count():
                w = self._cd_layout.takeAt(0).widget()
                if w:
                    w.deleteLater()

        # Tags

        # Histogram (only for images)
        if isinstance(item, PrismPixmapItem):
            pm = item.pixmap()
            self._hist_widget.update_from_pixmap(pm)
        else:
            self._hist_widget.clear()

    # ── Color distribution ────────────────────────

    def _build_color_distribution(self, item):
        """Compute and render color distribution for a pixmap item."""
        # Clear existing
        while self._cd_layout.count():
            w = self._cd_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        pm = item.pixmap()
        if pm is None or pm.isNull():
            return

        # Sample pixels (downscale to max 72px like analyze_color_group)
        img = pm.toImage()
        max_side = 72
        w, h = img.width(), img.height()
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            img = img.scaled(
                max(1, int(w * scale)), max(1, int(h * scale)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation)

        weights = {}
        for g in COLOR_GROUPS:
            weights[g['id']] = 0.0
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
                weights[gid] = weights.get(gid, 0.0) + wt
        total = sum(weights.values())
        if total < 1:
            return

        # Sort by weight desc, keep top 5
        sorted_groups = sorted(
            [(gid, weights[gid]) for gid in weights if weights[gid] > 0],
            key=lambda x: -x[1])[:5]

        # Color bar
        bar = _ColorBar(sorted_groups, total)
        bar.setFixedHeight(10)
        self._cd_layout.addWidget(bar)

        # Labels row
        labels_row = QtWidgets.QWidget()
        labels_layout = QtWidgets.QGridLayout(labels_row)
        labels_layout.setContentsMargins(0, 4, 0, 0)
        labels_layout.setSpacing(6)
        color_map = {g['id']: g for g in COLOR_GROUPS}
        for row, (gid, wt) in enumerate(sorted_groups):
            pct = int(round(wt / total * 100))
            info = color_map.get(gid, {})
            label = info.get('label', gid)
            chip = QtWidgets.QLabel()
            chip.setFixedSize(10, 10)
            chip.setStyleSheet(
                'background: %s; border-radius: 5px;' % info.get('color', '#888'))
            labels_layout.addWidget(chip, row, 0)
            txt = QtWidgets.QLabel('%s %d%%' % (label, pct))
            txt.setStyleSheet('color: #bbb;')
            labels_layout.addWidget(txt, row, 1)
        labels_layout.setColumnStretch(1, 1)
        self._cd_layout.addWidget(labels_row)


    def _on_title_changed(self, text):
        if not self._item:
            return
        old = getattr(self._item, '_title', '') or getattr(
            self._item, 'filename', '')
        if text == old:
            return
        self.scene.undo_stack.push(
            commands.ChangeMetadata([self._item], 'title', [text]))

    def _on_notes_changed(self):
        if not self._item:
            return
        new_notes = self._notes_edit.toPlainText()
        old_notes = getattr(self._item, '_notes', '')
        if new_notes == old_notes:
            return
        self.scene.undo_stack.push(
            commands.ChangeMetadata([self._item], 'notes', [new_notes]))

    def _on_category_changed(self, index):
        selected = self.scene.selectedItems(user_only=True)
        new_cats = self._cat_combo.currentData()
        if not selected or new_cats is None:
            return
        selected = [i for i in selected if list(i.categories) != new_cats]
        if not selected:
            return
        self.scene.undo_stack.push(
            commands.ChangeMetadata(selected, 'categories',
                                    [list(new_cats) for i in selected]))
        if hasattr(self.view, 'category_panel'):
            self.view.category_panel.update_counts()

    def _load_categories(self):
        return self.view.category_panel._load_categories()


class _ColorBar(QtWidgets.QWidget):
    def __init__(self, groups_with_weights, total, parent=None):
        super().__init__(parent)
        self._segments = []
        color_map = {g['id']: g for g in COLOR_GROUPS}
        for gid, wt in groups_with_weights:
            ratio = wt / total if total > 0 else 0
            hex_color = color_map.get(gid, {}).get('color', '#888')
            self._segments.append((ratio, hex_color))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        x = 0.0
        for i, (ratio, hex_color) in enumerate(self._segments):
            seg_w = ratio * w
            color = QtGui.QColor(hex_color)
            painter.fillRect(
                QtCore.QRectF(x, 0, seg_w + 0.5, h), color)
            x += seg_w
        painter.end()

class _HistogramWidget(QtWidgets.QWidget):
    """Professional brightness/color histogram with zone analysis."""

    # 5 tonal zones (Photoshop-style)
    ZONES = [
        ('暗部',    0,   51,  '#4a4a6a'),   # Shadows
        ('偏暗',   51,  102,  '#6a6a8a'),   # Darks
        ('中间调', 102, 153, '#8a8aaa'), # Midtones
        ('偏亮',  153, 204,  '#aaaacc'),   # Lights
        ('亮部',  204, 256,  '#ccccee'),   # Highlights
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bins = None
        self._stats = None
        self.setMinimumHeight(180)

    def clear(self):
        self._bins = None
        self._stats = None
        self.update()

    def update_from_pixmap(self, pm):
        if pm is None or pm.isNull():
            self.clear()
            return
        img = pm.toImage()
        max_side = 120
        w, h = img.width(), img.height()
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            img = img.scaled(
                max(1, int(w * scale)), max(1, int(h * scale)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation)
        lum = [0] * 256
        r_bins = [0] * 256
        g_bins = [0] * 256
        b_bins = [0] * 256
        total_pixels = 0
        sum_l = 0.0
        sum_l2 = 0.0
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() < 180:
                    continue
                rv, gv, bv = c.red(), c.green(), c.blue()
                lv = int(0.299 * rv + 0.587 * gv + 0.114 * bv)
                lv = min(255, max(0, lv))
                lum[lv] += 1
                r_bins[min(255, rv)] += 1
                g_bins[min(255, gv)] += 1
                b_bins[min(255, bv)] += 1
                total_pixels += 1
                sum_l += lv
                sum_l2 += lv * lv
        self._bins = (lum, r_bins, g_bins, b_bins)
        if total_pixels > 0:
            mean = sum_l / total_pixels
            variance = (sum_l2 / total_pixels) - (mean * mean)
            std = variance ** 0.5 if variance > 0 else 0
            zones = []
            for zname, zlo, zhi, zcolor in self.ZONES:
                cnt = sum(lum[zlo:zhi])
                pct = cnt / total_pixels * 100
                zones.append((zname, zlo, zhi, zcolor, pct))
            if std < 30:
                contrast_txt = '低对比度'
            elif std < 60:
                contrast_txt = '中等对比度'
            else:
                contrast_txt = '高对比度'
            if mean < 64:
                expo_txt = '曝光不足'
            elif mean < 100:
                expo_txt = '偏暗'
            elif mean < 160:
                expo_txt = '曝光正常'
            elif mean < 210:
                expo_txt = '偏亮'
            else:
                expo_txt = '过曝'
            self._stats = {
                'mean': mean,
                'std': std,
                'zones': zones,
                'contrast': contrast_txt,
                'exposure': expo_txt,
                'total': total_pixels,
            }
        else:
            self._stats = None
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        if self._bins is None or self._stats is None or w < 10 or h < 10:
            painter.setPen(QtGui.QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             '无数据')
            painter.end()
            return

        # Layout: graph top 50%, zone bars 22%, stats text 28%
        graph_h = int(h * 0.50)
        zone_h = int(h * 0.22)
        stats_y = graph_h + zone_h + 4
        margin = 4
        pw = w - margin * 2
        ph = graph_h - margin * 2

        lum, r_bins, g_bins, b_bins = self._bins
        max_val = max(max(lum), max(r_bins), max(g_bins), max(b_bins), 1)

        # Draw zone background bands
        for zname, zlo, zhi, zcolor, pct in self._stats['zones']:
            x1 = margin + (zlo / 256.0) * pw
            x2 = margin + (zhi / 256.0) * pw
            color = QtGui.QColor(zcolor)
            color.setAlpha(25)
            painter.fillRect(
                QtCore.QRectF(x1, margin, x2 - x1, ph), color)

        # Draw channels
        channels = [
            (r_bins, QtGui.QColor(255, 80, 80, 80)),
            (g_bins, QtGui.QColor(80, 255, 80, 80)),
            (b_bins, QtGui.QColor(80, 120, 255, 80)),
            (lum, QtGui.QColor(220, 220, 220, 160)),
        ]
        for bins, color in channels:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            path = QtGui.QPainterPath()
            path.moveTo(margin, graph_h - margin)
            step = pw / 256.0
            for i in range(256):
                bar_h = (bins[i] / max_val) * ph
                path.lineTo(margin + i * step, graph_h - margin - bar_h)
            path.lineTo(margin + 255 * step, graph_h - margin)
            path.closeSubpath()
            painter.drawPath(path)

        # Draw mean line
        mean_x = margin + (self._stats['mean'] / 256.0) * pw
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 200, 50), 1.5))
        painter.drawLine(
            QtCore.QPointF(mean_x, margin),
            QtCore.QPointF(mean_x, graph_h - margin))
        painter.setPen(QtGui.QColor(255, 200, 50))
        font = painter.font()
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRectF(mean_x - 20, 0, 40, margin + 2),
            Qt.AlignmentFlag.AlignCenter,
            'μ=%d' % int(self._stats['mean']))

        # Zone percentage bars
        zone_y = graph_h + 2
        bar_total_w = pw
        bar_h_px = zone_h - 6
        x_cursor = margin
        for zname, zlo, zhi, zcolor, pct in self._stats['zones']:
            seg_w = ((zhi - zlo) / 256.0) * bar_total_w
            color = QtGui.QColor(zcolor)
            color.setAlpha(180)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QtCore.QRectF(x_cursor, zone_y, seg_w - 1, bar_h_px),
                2, 2)
            painter.setPen(QtGui.QColor(240, 240, 255))
            font.setPixelSize(12)
            painter.setFont(font)
            if seg_w > 28:
                label_text = '%s\n%d%%' % (zname, int(pct))
                painter.drawText(
                    QtCore.QRectF(x_cursor, zone_y, seg_w - 1, bar_h_px),
                    Qt.AlignmentFlag.AlignCenter, label_text)
            x_cursor += seg_w

        # Stats text row
        stats = self._stats
        painter.setPen(QtGui.QColor(180, 180, 200))
        font.setPixelSize(13)
        painter.setFont(font)
        stats_text = '均值: %d  标准差: %d  %s  %s' % (
            int(stats['mean']), int(stats['std']),
            stats['contrast'], stats['exposure'])
        painter.drawText(
            QtCore.QRectF(margin, stats_y, pw, h - stats_y),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            stats_text)

        painter.end()

