"""Media library sidebar panel.

Category-based filtering with batched visibility updates.
"""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from prism import commands


logger = logging.getLogger(__name__)


class MediaLibraryPanel(QtWidgets.QWidget):
    counts_changed = QtCore.pyqtSignal(dict)
    categories_changed = QtCore.pyqtSignal()

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.scene = view.scene
        self._active_filter = None  # None = show all; ('category', name) = filter
        self._setup_ui()
        self._recount_timer = QtCore.QTimer(self)
        self._recount_timer.setSingleShot(True)
        self._recount_timer.setInterval(300)
        self._recount_timer.timeout.connect(self.update_counts)
        self.scene.changed.connect(self._schedule_recount)
        self.update_counts()

    def _schedule_recount(self):
        if not self._recount_timer.isActive():
            self._recount_timer.start()

    def _setup_ui(self):
        self.setStyleSheet(
            'QWidget { background-color: #1c1c1e; }'
            'QLabel { color: #e5e5e7; }'
        )
        self.setMinimumWidth(200)
        self.setMaximumWidth(16777215)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(8)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('\u641c\u7d22\u540d\u79f0\u3001\u8def\u5f84\u6216\u5907\u6ce8')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet(
            'QListWidget { background: transparent; border: none; '
            '  outline: none; color: #ffffff; }'
            'QListWidget::item { padding: 5px 10px; border-radius: 5px; '
            '  margin: 2px 0px; }'
            'QListWidget::item:hover { background: rgba(255,255,255,0.06); }'
            'QListWidget::item:selected { background: rgba(10,132,255,0.2); '
            '  color: #fff; font-weight: 500; }'
        )
        self.list_widget.currentItemChanged.connect(
            self._on_item_selected)
        self.list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(
            self._on_context_menu)
        layout.addWidget(self.list_widget, stretch=1)

        self.assign_button = QtWidgets.QPushButton(
            '\u5c06\u6240\u9009\u7d20\u6750\u79fb\u5165\u5206\u7c7b\u2026')
        self.assign_button.clicked.connect(self._assign_selected)
        layout.addWidget(self.assign_button)

        self.hint = QtWidgets.QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.scene.selectionChanged.connect(self._update_selection)
        self.scene.metadata_changed.connect(self._on_metadata_changed)
        self._rebuild_list()

    # ── List building ─────────────────────────────────────────

    def _rebuild_list(self):
        """Rebuild the entire list widget contents."""
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()

            # Category header with + button
            cat_title_item = QtWidgets.QListWidgetItem()
            cat_title_item.setData(Qt.ItemDataRole.UserRole, {'type': 'header'})
            cat_title_item.setFlags(Qt.ItemFlag.NoItemFlags)
            cat_title_item.setSizeHint(QtCore.QSize(0, 42))
            self.list_widget.addItem(cat_title_item)
            header = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(header)
            row.setContentsMargins(10, 0, 6, 0)
            lbl = QtWidgets.QLabel('\u5206\u7c7b')
            lbl.setStyleSheet('font-size: 14px; font-weight: 600;')
            row.addWidget(lbl)
            row.addStretch()
            self.add_button = QtWidgets.QToolButton()
            self.add_button.setText('+')
            self.add_button.setAccessibleName('\u65b0\u5efa\u5206\u7c7b')
            self.add_button.setToolTip('\u65b0\u5efa\u5206\u7c7b')
            self.add_button.setFixedSize(32, 32)
            self.add_button.setStyleSheet(
                'QToolButton { padding: 0; font-size: 24px; }')
            self.add_button.clicked.connect(self.add_category)
            row.addWidget(self.add_button)
            self.list_widget.setItemWidget(cat_title_item, header)

            # User categories
            self._cat_items = {}
            categories = self._load_categories()
            counts = self._calc_counts()
            for cat in categories:
                c = counts.get('categories', {}).get(cat, 0)
                item = QtWidgets.QListWidgetItem(f'  {cat}  ({c})')
                item.setData(Qt.ItemDataRole.UserRole,
                             {'type': 'category', 'name': cat})
                item.setSizeHint(QtCore.QSize(0, 42))
                self.list_widget.addItem(item)
                self._cat_items[cat] = item

            # Restore active selection or auto-select first category
            if (self._active_filter
                    and self._active_filter[0] == 'category'
                    and self._active_filter[1] in self._cat_items):
                self.list_widget.setCurrentItem(
                    self._cat_items[self._active_filter[1]])
            elif self._cat_items:
                first_key = next(iter(self._cat_items))
                self.list_widget.setCurrentItem(
                    self._cat_items[first_key])
                self._active_filter = ('category', first_key)
            else:
                self._active_filter = None
        finally:
            self.list_widget.blockSignals(False)

    # ── Count updates ─────────────────────────────────────────

    def update_counts(self):
        names = self._load_categories()
        changed = list(self._cat_items) != names
        if changed:
            self._rebuild_list()
        counts = self._calc_counts()
        for cat, item in self._cat_items.items():
            c = counts['categories'].get(cat, 0)
            item.setText(f'  {cat}  ({c})')
            item.setToolTip(cat)
        self._apply_filter()
        self._update_selection()
        self.counts_changed.emit(counts)
        if changed:
            self.categories_changed.emit()

    def _calc_counts(self):
        """Count items per category."""
        result = {'categories': {}}
        for c in self._load_categories():
            result['categories'][c] = 0
        for item in self.scene.items():
            if not hasattr(item, 'save_id'):
                continue
            for cat in getattr(item, '_categories', []):
                if cat in result['categories']:
                    result['categories'][cat] += 1
        return result

    # ── Filtering (batched for performance) ───────────────────

    def _on_item_selected(self, current, previous):
        if current:
            data = current.data(Qt.ItemDataRole.UserRole)
            if data and data['type'] == 'category':
                self._active_filter = ('category', data['name'])
                self.update_counts()
                self.view.on_action_fit_scene()

    def clear_filter(self):
        self._active_filter = None
        self.search.clear()
        self.list_widget.clearSelection()
        self.update_counts()

    def _apply_filter(self):
        """Batched visibility update: compute first, apply with signals blocked."""
        active = self._active_filter
        query = self.search.text().strip().casefold()

        # Filter category list items by name when searching
        for cat_name, list_item in getattr(self, '_cat_items', {}).items():
            if query:
                list_item.setHidden(query not in cat_name.casefold())
            else:
                list_item.setHidden(False)

        # Phase 1: compute visibility (no scene mutations)
        changes = []
        visible = 0
        for item in self.scene.items_for_save():
            if active and active[0] == 'category':
                cats = getattr(item, '_categories', [])
                show = active[1] in cats
            else:
                show = True
            if query:
                text = ' '.join(
                    str(getattr(item, f, '') or '')
                    for f in ('_title', 'filename', '_notes'))
                show = show and query in text.casefold()
            if item.isVisible() != show:
                changes.append((item, show))
            visible += bool(show)

        # Phase 2: batch apply with signals blocked
        if changes:
            vp = self.view.viewport() if hasattr(self.view, 'viewport') else None
            if vp:
                vp.setUpdatesEnabled(False)
            self.scene.blockSignals(True)
            try:
                for item, show in changes:
                    item.setVisible(show)
            finally:
                self.scene.blockSignals(False)
                if vp:
                    vp.setUpdatesEnabled(True)
                self.scene.changed.emit([QtCore.QRectF()])

        self.hint.setText(
            f'当前显示 {visible} 个素材'
            if visible else
            '没有匹配的素材')

    def _update_selection(self):
        count = len(self.scene.selectedItems(user_only=True))
        self.assign_button.setEnabled(bool(count))
        self.assign_button.setText(
            f'\u5c06\u6240\u9009 {count} \u4e2a\u7d20\u6750\u79fb\u5165\u5206\u7c7b\u2026'
            if count else
            '\u5148\u5728\u753b\u5e03\u9009\u62e9\u7d20\u6750')

    def _assign_selected(self):
        menu = QtWidgets.QMenu(self)
        self.build_category_menu(menu)
        menu.exec(self.assign_button.mapToGlobal(
            self.assign_button.rect().bottomLeft()))

    # ── Category management ───────────────────────────────────

    def _load_categories(self):
        names = list(self.scene.category_names)
        for item in self.scene.items_for_save():
            for name in getattr(item, '_categories', []):
                if name and name not in names:
                    names.append(name)
        return names

    def _save_categories(self, categories):
        self.scene.category_names = list(categories)

    def add_category(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, '\u65b0\u5efa\u5206\u7c7b',
            '\u5206\u7c7b\u540d\u79f0\uff1a')
        if not ok or not name.strip():
            return
        name = name.strip()
        cats = self._load_categories()
        if name in cats:
            QtWidgets.QMessageBox.warning(
                self, '\u63d0\u793a',
                '\u8be5\u5206\u7c7b\u5df2\u5b58\u5728')
            return
        self.scene.undo_stack.push(ChangeCategory(self, cats + [name]))

    def rename_category(self, old_name):
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, '\u91cd\u547d\u540d\u5206\u7c7b',
            '\u65b0\u540d\u79f0\uff1a', text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        cats = self._load_categories()
        if new_name in cats:
            QtWidgets.QMessageBox.warning(
                self, '\u63d0\u793a',
                '\u8be5\u5206\u7c7b\u5df2\u5b58\u5728')
            return
        self.scene.undo_stack.push(ChangeCategory(
            self,
            [new_name if c == old_name else c for c in cats],
            old_name, new_name))

    def delete_category(self, name):
        reply = QtWidgets.QMessageBox.question(
            self, '\u5220\u9664\u5206\u7c7b',
            f'\u786e\u5b9a\u5220\u9664\u5206\u7c7b\u300c{name}\u300d\u5417\uff1f\n'
            '\u5176\u4e2d\u7684\u7d20\u6750\u4f1a\u8f6c\u4e3a\u672a\u5206\u7c7b\uff0c'
            '\u7d20\u6750\u672c\u8eab\u4e0d\u4f1a\u5220\u9664\u3002')
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.scene.undo_stack.push(ChangeCategory(
            self, [c for c in self._load_categories() if c != name], name))

    def _on_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data['type'] == 'category':
            menu = QtWidgets.QMenu(self)
            act_rename = menu.addAction('\u91cd\u547d\u540d')
            act_delete = menu.addAction('\u5220\u9664')
            action = menu.exec(
                self.list_widget.mapToGlobal(pos))
            if action == act_rename:
                self.rename_category(data['name'])
            elif action == act_delete:
                self.delete_category(data['name'])

    # ── Assign items to category (public API) ────────────────

    def assign_category(self, items, category_name):
        values = [category_name] if category_name else []
        items = [i for i in items if list(i.categories) != values]
        if items:
            self.scene.undo_stack.push(commands.ChangeMetadata(
                items, 'categories', [list(values) for i in items]))

    def build_category_menu(self, parent_menu):
        for cat in self._load_categories():
            act = parent_menu.addAction(cat)
            act.triggered.connect(
                lambda checked=False, c=cat: self._do_assign(c))
        parent_menu.addSeparator()
        parent_menu.addAction(
            '\u79fb\u81f3\u672a\u5206\u7c7b',
            lambda: self._do_assign(None))
        parent_menu.addAction(
            '\u65b0\u5efa\u5206\u7c7b\u2026', self.add_category)

    def _do_assign(self, category_name):
        selected = self.scene.selectedItems(user_only=True)
        if not selected:
            return
        self.assign_category(selected, category_name)

    def force_rebuild(self):
        self.search.clear()
        self._rebuild_list()
        self.update_counts()
        self.categories_changed.emit()

    def _on_metadata_changed(self):
        self.update_counts()


class ChangeCategory(QtGui.QUndoCommand):
    """Keep catalogue, item membership and current filter together in undo."""
    def __init__(self, panel, names, old_name=None, new_name=None):
        super().__init__('\u4fee\u6539\u5206\u7c7b')
        self.panel = panel
        self.before_names = panel._load_categories()
        self.after_names = list(names)
        self.before_filter = panel._active_filter
        self.after_filter = self.before_filter
        if old_name and self.before_filter == ('category', old_name):
            self.after_filter = (
                ('category', new_name) if new_name else None)
        self.items = [i for i in panel.scene.items_for_save()
                      if old_name and old_name in i.categories]
        self.before = [list(i.categories) for i in self.items]
        self.after = [
            [new_name if c == old_name else c for c in cats
             if c != old_name or new_name]
            for cats in self.before]

    def _apply(self, names, values, active):
        self.panel.scene.category_names = list(names)
        for item, cats in zip(self.items, values):
            item._categories = list(cats)
        self.panel._active_filter = active
        self.panel._rebuild_list()
        self.panel.scene.metadata_changed.emit()
        self.panel.categories_changed.emit()

    def redo(self):
        self._apply(self.after_names, self.after, self.after_filter)

    def undo(self):
        self._apply(self.before_names, self.before, self.before_filter)
