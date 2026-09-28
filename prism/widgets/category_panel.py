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

"""Side panel for categories, tags, and notes management."""

import json
import logging
import os.path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from prism import commands


logger = logging.getLogger(__name__)

# Path to default categories config
_CATEGORIES_JSON = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'categories.json')


def load_category_tree():
    """Load the category tree from config/categories.json.

    Returns a list of top-level category dicts, each with 'name'
    and optional 'children' keys.
    """
    try:
        with open(_CATEGORIES_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('categories', [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f'Could not load categories.json: {e}')
        return []


def flatten_categories(tree, prefix=''):
    """Flatten the category tree into a list of full paths.

    E.g. [{'name': '角色', 'children': [{'name': '主角'}]}]
      -> ['角色', '角色/主角']
    """
    paths = []
    for node in tree:
        full_path = f"{prefix}/{node['name']}" if prefix else node['name']
        paths.append(full_path)
        children = node.get('children', [])
        if children:
            paths.extend(flatten_categories(children, full_path))
    return paths


class CategoryPanelWidget(QtWidgets.QWidget):
    """The main side panel containing categories, tags, and notes."""

    filter_requested = QtCore.pyqtSignal(list, list)  # categories, tags
    clear_filter_requested = QtCore.pyqtSignal()

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.scene = view.scene
        self._updating = False  # guard against recursive updates
        self._selected_categories = set()
        self._selected_tags = set()

        self._setup_ui()
        self._connect_signals()
        self.refresh_panel()

    def _setup_ui(self):
        # Apple-style dark sidebar
        self.setStyleSheet(
            'QWidget { background-color: #2c2c2e; }'
            'QLabel { color: #f5f5f7; }'
            'QTreeWidget { background-color: rgba(28, 28, 30, 0.6);'
            '  border: 1px solid rgba(255,255,255,0.06); border-radius: 6px;'
            '  color: #f5f5f7; }'
            'QTreeWidget::item:selected { background-color: rgba(10,132,255,0.4); }'
            'QTreeWidget::item:hover { background-color: rgba(255,255,255,0.04); }'
            'QListWidget { background-color: rgba(28, 28, 30, 0.6);'
            '  border: 1px solid rgba(255,255,255,0.06); border-radius: 6px;'
            '  color: #f5f5f7; }'
            'QListWidget::item:selected { background-color: rgba(10,132,255,0.4); }'
            'QTextEdit { background-color: rgba(28, 28, 30, 0.6);'
            '  border: 1px solid rgba(255,255,255,0.06); border-radius: 6px;'
            '  color: #f5f5f7; }'
            'QPushButton { background-color: rgba(58,58,60,0.9);'
            '  border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;'
            '  padding: 4px 12px; color: #f5f5f7; }'
            'QPushButton:hover { background-color: rgba(72,72,74,0.95); }'
        )
        self.setMinimumWidth(200)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QtWidgets.QLabel('分类与备注')
        header.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: rgba(245,245,247,0.6);')
        layout.addWidget(header)

        # Splitter for flexible layout
        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        # Category section
        cat_widget = QtWidgets.QWidget()
        cat_layout = QtWidgets.QVBoxLayout(cat_widget)
        cat_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.setSpacing(4)

        cat_header = QtWidgets.QLabel('分类')
        cat_header.setStyleSheet('font-weight: bold; font-size: 12px;')
        cat_layout.addWidget(cat_header)

        self.category_tree = QtWidgets.QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        cat_layout.addWidget(self.category_tree)

        cat_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_clear_cat_filter = QtWidgets.QPushButton('清除分类筛选')
        self.btn_clear_cat_filter.setEnabled(False)
        cat_btn_layout.addWidget(self.btn_clear_cat_filter)
        cat_layout.addLayout(cat_btn_layout)

        splitter.addWidget(cat_widget)

        # Tag section
        tag_widget = QtWidgets.QWidget()
        tag_layout = QtWidgets.QVBoxLayout(tag_widget)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.setSpacing(4)

        tag_header = QtWidgets.QLabel('标签')
        tag_header.setStyleSheet('font-weight: bold; font-size: 12px;')
        tag_layout.addWidget(tag_header)

        self.tag_list = QtWidgets.QListWidget()
        self.tag_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        tag_layout.addWidget(self.tag_list)

        tag_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_clear_tag_filter = QtWidgets.QPushButton('清除标签筛选')
        self.btn_clear_tag_filter.setEnabled(False)
        tag_btn_layout.addWidget(self.btn_clear_tag_filter)
        tag_layout.addLayout(tag_btn_layout)

        splitter.addWidget(tag_widget)

        # Notes section
        notes_widget = QtWidgets.QWidget()
        notes_layout = QtWidgets.QVBoxLayout(notes_widget)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(4)

        notes_header = QtWidgets.QLabel('备注')
        notes_header.setStyleSheet('font-weight: bold; font-size: 12px;')
        notes_layout.addWidget(notes_header)

        self.notes_edit = QtWidgets.QTextEdit()
        self.notes_edit.setPlaceholderText('选中素材后可编辑备注...')
        notes_layout.addWidget(self.notes_edit)

        self.multi_select_label = QtWidgets.QLabel('')
        self.multi_select_label.setStyleSheet('color: rgba(245,245,247,0.4);')
        self.multi_select_label.hide()
        notes_layout.addWidget(self.multi_select_label)

        splitter.addWidget(notes_widget)

    def _connect_signals(self):
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.scene.metadata_changed.connect(self.refresh_panel)
        self.category_tree.itemSelectionChanged.connect(
            self._on_category_filter_changed)
        self.tag_list.itemChanged.connect(self._on_tag_filter_changed)
        self.btn_clear_cat_filter.clicked.connect(self._on_clear_cat_filter)
        self.btn_clear_tag_filter.clicked.connect(self._on_clear_tag_filter)
        self.notes_edit.textChanged.connect(self._on_notes_changed)

    def _on_selection_changed(self):
        """When scene selection changes, update the panel display."""
        if self._updating:
            return
        self.refresh_panel()

    def refresh_panel(self):
        """Refresh all panel sections based on current scene state."""
        self._updating = True
        try:
            # Block signals during rebuild to prevent signal recursion
            self.category_tree.blockSignals(True)
            self.tag_list.blockSignals(True)
            try:
                self._refresh_category_tree()
                self._refresh_tag_list()
            finally:
                self.category_tree.blockSignals(False)
                self.tag_list.blockSignals(False)
            self._refresh_notes()
        finally:
            self._updating = False

    def _refresh_category_tree(self):
        """Rebuild the category tree widget."""
        self.category_tree.clear()
        tree_data = load_category_tree()
        self._build_tree_items(tree_data, parent=None)
        # Restore selected categories for filter
        self._restore_category_selection()

    def _build_tree_items(self, nodes, parent, prefix=''):
        """Recursively build QTreeWidgetItems from category tree data."""
        for node in nodes:
            name = node['name']
            full_path = f"{prefix}/{name}" if prefix else name
            item = QtWidgets.QTreeWidgetItem([name])
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            if parent:
                parent.addChild(item)
            else:
                self.category_tree.addTopLevelItem(item)
            children = node.get('children', [])
            if children:
                self._build_tree_items(children, item, full_path)

    def _restore_category_selection(self):
        """Re-select tree items that match _selected_categories."""
        # Do NOT touch self._updating here — caller (refresh_panel) owns it
        for i in range(self.category_tree.topLevelItemCount()):
            self._select_tree_item_recursive(
                self.category_tree.topLevelItem(i))

    def _select_tree_item_recursive(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path in self._selected_categories:
            item.setSelected(True)
        for i in range(item.childCount()):
            self._select_tree_item_recursive(item.child(i))

    def _refresh_tag_list(self):
        """Rebuild the tag list widget showing all tags with counts."""
        # Remember checked state
        checked_tags = set()
        for i in range(self.tag_list.count()):
            tag_item = self.tag_list.item(i)
            if tag_item.checkState() == Qt.CheckState.Checked:
                tag_name = tag_item.data(Qt.ItemDataRole.UserRole)
                checked_tags.add(tag_name)
        # Also include from _selected_tags
        checked_tags.update(self._selected_tags)

        self.tag_list.clear()
        tag_counts = self.scene.get_all_tags()

        # Also include tags currently on selected items that may not
        # be in the global count yet
        for item in self.scene.selectedItems(user_only=True):
            for tag in getattr(item, '_tags', []):
                if tag not in tag_counts:
                    tag_counts[tag] = 0

        for tag in sorted(tag_counts.keys()):
            count = tag_counts[tag]
            label = f"{tag} ({count})"
            tag_item = QtWidgets.QListWidgetItem(label)
            tag_item.setData(Qt.ItemDataRole.UserRole, tag)
            tag_item.setFlags(
                tag_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if tag in checked_tags:
                tag_item.setCheckState(Qt.CheckState.Checked)
            else:
                tag_item.setCheckState(Qt.CheckState.Unchecked)
            self.tag_list.addItem(tag_item)

    def _refresh_notes(self):
        """Update the notes editor based on current selection."""
        selected = self.scene.selectedItems(user_only=True)
        if not selected:
            self.notes_edit.clear()
            self.notes_edit.setEnabled(False)
            self.notes_edit.setPlaceholderText('未选中素材')
            self.multi_select_label.hide()
        elif len(selected) == 1:
            self.notes_edit.setEnabled(True)
            self.notes_edit.setPlaceholderText(
                '选中素材后可编辑备注...')
            self.multi_select_label.hide()
            notes = getattr(selected[0], '_notes', '')
            self.notes_edit.blockSignals(True)
            self.notes_edit.setPlainText(notes)
            self.notes_edit.blockSignals(False)
        else:
            self.notes_edit.setEnabled(False)
            self.notes_edit.clear()
            self.notes_edit.setPlaceholderText('')
            self.multi_select_label.setText(
                f'（已选中 {len(selected)} 个素材）')
            self.multi_select_label.show()

    def _on_category_filter_changed(self):
        """Handle category tree selection change for filtering."""
        if self._updating:
            return
        self._selected_categories = set()
        for item in self.category_tree.selectedItems():
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                self._selected_categories.add(path)

        self.btn_clear_cat_filter.setEnabled(bool(self._selected_categories))
        self._apply_filter()

    def _on_tag_filter_changed(self, item):
        """Handle tag checkbox toggle for filtering."""
        if self._updating:
            return
        self._selected_tags = set()
        for i in range(self.tag_list.count()):
            tag_item = self.tag_list.item(i)
            if tag_item.checkState() == Qt.CheckState.Checked:
                tag_name = tag_item.data(Qt.ItemDataRole.UserRole)
                self._selected_tags.add(tag_name)

        self.btn_clear_tag_filter.setEnabled(bool(self._selected_tags))
        self._apply_filter()

    def _on_clear_cat_filter(self):
        """Clear category filter."""
        self._selected_categories.clear()
        self._updating = True
        self.category_tree.clearSelection()
        self._updating = False
        self.btn_clear_cat_filter.setEnabled(False)
        self._apply_filter()

    def _on_clear_tag_filter(self):
        """Clear tag filter."""
        self._selected_tags.clear()
        self._updating = True
        for i in range(self.tag_list.count()):
            self.tag_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._updating = False
        self.btn_clear_tag_filter.setEnabled(False)
        self._apply_filter()

    def _apply_filter(self):
        """Apply the current combined filter to the scene."""
        cats = list(self._selected_categories) if self._selected_categories else None
        tags = list(self._selected_tags) if self._selected_tags else None
        if cats or tags:
            self.scene.filter_items(categories=cats, tags=tags)
        else:
            self.scene.clear_filter()

    def _on_notes_changed(self):
        """When user edits notes in the panel, apply to selected item."""
        if self._updating:
            return
        selected = self.scene.selectedItems(user_only=True)
        if len(selected) != 1:
            return
        item = selected[0]
        new_notes = self.notes_edit.toPlainText()
        old_notes = getattr(item, '_notes', '')
        if new_notes == old_notes:
            return
        # Push undo command
        self.scene.undo_stack.push(
            commands.ChangeMetadata([item], 'notes', [new_notes]))

    # Public API for right-click menu integration

    def assign_category(self, items, category_path):
        """Toggle a category on the given items."""
        for item in items:
            cats = list(getattr(item, '_categories', []))
            if category_path in cats:
                cats.remove(category_path)
            else:
                cats.append(category_path)
            self.scene.undo_stack.push(
                commands.ChangeMetadata([item], 'categories', [cats]))

    def assign_tag(self, items, tag):
        """Toggle a tag on the given items."""
        for item in items:
            tags = list(getattr(item, '_tags', []))
            if tag in tags:
                tags.remove(tag)
            else:
                tags.append(tag)
            self.scene.undo_stack.push(
                commands.ChangeMetadata([item], 'tags', [tags]))

    def add_new_tag(self, items, tag):
        """Add a new tag to the given items (no toggle)."""
        for item in items:
            tags = list(getattr(item, '_tags', []))
            if tag not in tags:
                tags.append(tag)
                self.scene.undo_stack.push(
                    commands.ChangeMetadata([item], 'tags', [tags]))
