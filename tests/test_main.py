from unittest.mock import patch, MagicMock

from PyQt6 import QtCore

from prism.__main__ import PrismMainWindow, main
from prism.assets import BeeAssets
from prism.view import PrismGraphicsView


@patch('PyQt6.QtWidgets.QWidget.show')
def test_prism_mainwindow_init(show_mock, qapp):
    window = PrismMainWindow(qapp)
    assert window.windowTitle() == 'Prism'
    assert BeeAssets().logo == BeeAssets().logo
    assert window.windowIcon()
    assert window.contentsMargins() == QtCore.QMargins(0, 0, 0, 0)
    assert isinstance(window.view, PrismGraphicsView)
    show_mock.assert_called()


@patch('prism.view.PrismGraphicsView.open_from_file')
def test_prismapplication_fileopenevent(open_mock, qapp, main_window):
    event = MagicMock()
    event.type.return_value = QtCore.QEvent.Type.FileOpen
    event.file.return_value = 'test.prism'
    assert qapp.event(event) is True
    open_mock.assert_called_once_with('test.prism')


@patch('prism.__main__.PrismApplication')
@patch('prism.__main__.CommandlineArgs')
@patch('prism.config.PrismSettings.on_startup')
def test_main(startup_mock, args_mock, app_mock, qapp):
    app_mock.return_value = qapp
    args_mock.return_value.filename = None
    args_mock.return_value.loglevel = 'WARN'
    args_mock.return_value.debug_raise_error = ''

    with patch.object(qapp, 'exec') as exec_mock:
        main()
        exec_mock.assert_called_once_with()

    args_mock.assert_called_once_with(with_check=True)
    startup_mock.assert_called()
