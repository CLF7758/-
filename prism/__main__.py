#!/usr/bin/env python3

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

import logging
import os
import platform
import signal
import sys

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from prism import constants
from prism.assets import BeeAssets
from prism.config import CommandlineArgs, PrismSettings, logfile_name
from prism.utils import create_palette_from_dict
from prism.view import PrismGraphicsView
from prism.widgets.color_filter import ColorFilterBar

logger = logging.getLogger(__name__)


class PrismApplication(QtWidgets.QApplication):

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.FileOpen:
            for widget in self.topLevelWidgets():
                if isinstance(widget, PrismMainWindow):
                    widget.view.open_from_file(event.file())
                    return True
            return False
        else:
            return super().event(event)




class PrismMainWindow(QtWidgets.QMainWindow):
    """A standard desktop window with independently resizable side panels."""

    def __init__(self, app):
        super().__init__()
        app.setOrganizationName(constants.APPNAME)
        app.setApplicationName(constants.APPNAME)
        self.setWindowIcon(BeeAssets().logo)
        self.view = PrismGraphicsView(app, self)
        self.setMinimumSize(760, 520)
        self.resize(1280, 820)
        geom = self.view.settings.value('MainWindow/geometry')
        if geom is not None:
            self.restoreGeometry(geom)

        self.color_filter = ColorFilterBar(self.view)
        self._recount_timer = QtCore.QTimer(self)
        self._recount_timer.setSingleShot(True)
        self._recount_timer.setInterval(300)
        self._recount_timer.timeout.connect(self.color_filter.recount)
        self.view.scene.changed.connect(self._schedule_recount)

        from prism.widgets.detail_panel import DetailPanel
        self.view._detail_panel = DetailPanel(self.view)
        self.view.category_panel.categories_changed.connect(
            self.view._detail_panel._on_selection_changed)

        outer = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        colors = QtWidgets.QScrollArea()
        colors.setWidgetResizable(True)
        colors.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        colors.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        colors.setFixedHeight(84)
        colors.setWidget(self.color_filter)
        layout.addWidget(colors)

        self.splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(self.view.category_panel)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.view._detail_panel)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([240, 720, 320])
        state = self.view.settings.value('MainWindow/splitter')
        if state is not None:
            self.splitter.restoreState(state)
        layout.addWidget(self.splitter, 1)
        self.setCentralWidget(outer)

        self._build_layout_menu()
        self.view.scene.selectionChanged.connect(self._sync_detail_visibility)
        self._sync_detail_visibility()

        self.view.category_panel.counts_changed.connect(self._update_status)
        self.view.scene.selectionChanged.connect(
            lambda: self._update_status(self.view.category_panel._calc_counts()))
        self.view.category_panel.update_counts()
        self.color_filter.recount()
        self.view.update_window_title()
        self.show()

    def _build_layout_menu(self):
        menu = self.view.context_menu.addMenu('界面布局')
        self._category_action = menu.addAction('显示分类面板')
        self._category_action.setCheckable(True)
        self._category_action.setChecked(True)
        self._category_action.toggled.connect(self.view.category_panel.setVisible)
        menu.addAction('重置面板宽度', self.reset_layout)
        fonts = menu.addMenu('字号')
        self.font_actions = QtGui.QActionGroup(self)
        self.font_actions.setExclusive(True)
        current = self.view.settings.value('Interface/font_preset', '中')
        for label, size in [('小', 14), ('中', 16), ('标准', 18)]:
            action = fonts.addAction(label)
            action.setCheckable(True)
            action.setData(size)
            self.font_actions.addAction(action)
            action.setChecked(label == current)
            action.triggered.connect(lambda checked, a=action: self._change_font_size(a))
        selected = self.font_actions.checkedAction() or self.font_actions.actions()[1]
        selected.setChecked(True)
        self._change_font_size(selected)

    def _change_font_size(self, action):
        self.view.settings.setValue('Interface/font_preset', action.text())
        size = action.data()
        self.setStyleSheet(
            f'QWidget {{ font-size: {size}px; font-family: "Microsoft YaHei UI", "Segoe UI"; }}')

    def _sync_detail_visibility(self):
        selected = self.view.scene.selectedItems(user_only=True)
        visible = any(getattr(i, 'TYPE', '') in ('pixmap', 'video') for i in selected)
        was_hidden = self.view._detail_panel.isHidden()
        self.view._detail_panel.setVisible(visible)
        if visible and was_hidden:
            sizes = self.splitter.sizes()
            sizes[2] = 320
            sizes[1] = max(200, self.width() - sizes[0] - 336)
            self.splitter.setSizes(sizes)

    def reset_layout(self):
        self._category_action.setChecked(True)
        self.view.category_panel.show()
        self._sync_detail_visibility()
        self.splitter.setSizes([240, max(240, self.width() - 576), 320])

    def _update_status(self, counts):
        selected = len(self.view.scene.selectedItems(user_only=True))
        total = sum(1 for i in self.view.scene.items() if hasattr(i, 'save_id'))
        visible = sum(i.isVisible() for i in self.view.scene.items_for_save())
        self.statusBar().showMessage(
            f'共 {total} 个素材 · 当前显示 {visible} · 已选 {selected}')

    def _schedule_recount(self):
        # A playing video continuously changes the scene; don't starve updates.
        if not self._recount_timer.isActive():
            self._recount_timer.start()

    def closeEvent(self, event):
        worker = getattr(self.view, 'worker', None)
        if isinstance(worker, QtCore.QThread) and worker.isRunning():
            event.ignore()
            return
        if not self.view.get_confirmation_unsaved_changes(
                '有尚未保存的修改。确认放弃这些修改并关闭窗口吗？'):
            event.ignore()
            return
        self.view.settings.setValue('MainWindow/geometry', self.saveGeometry())
        self.view.settings.setValue('MainWindow/splitter', self.splitter.saveState())
        self.view.scene.deselect_all_items()
        event.accept()


def safe_timer(timeout, func, *args, **kwargs):
    """Create a timer that is safe against garbage collection and
    overlapping calls.
    See: http://ralsina.me/weblog/posts/BB974.html
    """
    def timer_event():
        try:
            func(*args, **kwargs)
        finally:
            QtCore.QTimer.singleShot(timeout, timer_event)
    QtCore.QTimer.singleShot(timeout, timer_event)


def handle_sigint(signum, frame):
    logger.info('Received interrupt. Exiting...')
    QtWidgets.QApplication.quit()


def handle_uncaught_exception(exc_type, exc, traceback):
    logger.critical('Unhandled exception',
                    exc_info=(exc_type, exc, traceback))
    QtWidgets.QApplication.quit()


sys.excepthook = handle_uncaught_exception


def _register_file_association():
    """Register .prism file type with Windows (HKCU, no admin needed)."""
    if sys.platform != 'win32':
        return
    try:
        import winreg
        # Determine exe path
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
            icon_path = os.path.join(sys._MEIPASS, 'prism', 'assets', 'logo.ico')
        else:
            exe_path = os.path.abspath(sys.argv[0])
            icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'logo.ico')

        # Convert backslashes for registry
        exe_path = exe_path.replace('/', '\\')
        icon_path = icon_path.replace('/', '\\')

        # Register file extension
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\.prism')
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'Prism.File')
        winreg.CloseKey(key)

        # Register file type
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\Prism.File')
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'Prism Project')
        winreg.CloseKey(key)

        # Set default icon
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\Prism.File\DefaultIcon')
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, f'"{icon_path}"')
        winreg.CloseKey(key)

        # Set open command
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\Prism.File\shell\open\command')
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, f'"{exe_path}" "%1"')
        winreg.CloseKey(key)

        logger.debug(f'Registered .prism file association: {exe_path}')
    except Exception as e:
        logger.debug(f'File association registration failed: {e}')


def main():
    logger.info(f'Starting {constants.APPNAME} version {constants.VERSION}')
    logger.debug('System: %s', ' '.join(platform.uname()))
    logger.debug('Python: %s', platform.python_version())
    logger.debug('LD_LIBRARY_PATH: %s', os.environ.get('LD_LIBRARY_PATH'))
    settings = PrismSettings()
    logger.info(f'Using settings: {settings.fileName()}')
    logger.info(f'Logging to: {logfile_name()}')
    settings.on_startup()
    args = CommandlineArgs(with_check=True)  # Force checking
    assert not args.debug_raise_error, args.debug_raise_error

    app = PrismApplication(sys.argv)
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 12))
    palette = create_palette_from_dict(constants.COLORS)
    app.setPalette(palette)

    # Load Apple-style QSS theme stylesheet
    # In PyInstaller, assets are in sys._MEIPASS; in dev, relative to __file__
    if getattr(sys, 'frozen', False):
        _assets_dir = os.path.join(sys._MEIPASS, 'prism', 'assets')
    else:
        _assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    qss_path = os.path.join(_assets_dir, 'theme.qss')
    if os.path.exists(qss_path):
        with open(qss_path, 'r', encoding='utf-8') as f:
            qss = f.read()
        # Resolve icon paths to absolute; use forward slashes for QSS
        # (backslashes are treated as escape chars by Qt's CSS parser)
        icons_dir = os.path.join(_assets_dir, 'icons').replace(os.sep, '/')
        qss = qss.replace('url(assets/icons/', f'url({icons_dir}/')
        app.setStyleSheet(qss)
        logger.debug(f'Loaded theme from {qss_path}')

    bee = PrismMainWindow(app)  # NOQA:F841

    # Register .prism file association (HKCU, no admin needed)
    _register_file_association()

    signal.signal(signal.SIGINT, handle_sigint)
    # Repeatedly run python-noop to give the interpreter time to
    # handle signals
    safe_timer(50, lambda: None)

    app.exec()
    del bee
    del app
    logger.debug('Prism closed')
    QtCore.qInstallMessageHandler(None)


if __name__ == '__main__':
    main()  # pragma: no cover
