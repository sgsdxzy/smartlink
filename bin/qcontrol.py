import sys
import os
import asyncio
import json
from collections import OrderedDict

from PyQt5.QtCore import Qt, QEvent, QTimer
# from PyQt5.QtGui import
from PyQt5.QtWidgets import (QTabBar, QTabWidget, QApplication, QLineEdit,
                             QWidget, QStyleFactory, QHBoxLayout, QVBoxLayout, QMainWindow, QPushButton,
                             QFrame)

from quamash import QEventLoop
from smartlink.qtpanel import NodePanel


class EditableTabBar(QTabBar):
    """A QTabBar with editable tab names."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editor = QLineEdit(self)
        self._editor.setWindowFlags(Qt.Popup)
        self._editor.setFocusProxy(self)
        self._editor.editingFinished.connect(self.handleEditingFinished)
        self._editor.installEventFilter(self)

    def eventFilter(self, widget, event):
        if ((event.type() == QEvent.MouseButtonPress
             and not self._editor.geometry().contains(event.globalPos()))
            or (event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Escape)):
            self._editor.hide()
            return True
        return super().eventFilter(widget, event)

    def mouseDoubleClickEvent(self, event):
        index = self.tabAt(event.pos())
        if index >= 0:
            self.editTab(index)

    def editTab(self, index):
        rect = self.tabRect(index)
        self._editor.setFixedSize(rect.size())
        self._editor.move(self.parent().mapToGlobal(rect.topLeft()))
        self._editor.setText(self.tabText(index))
        if not self._editor.isVisible():
            self._editor.show()

    def handleEditingFinished(self):
        index = self.currentIndex()
        if index >= 0:
            self._editor.hide()
            self.setTabText(index, self._editor.text())


class EditableTabWidget(QTabWidget):
    """A QTabWidget with editable tab names."""

    def __init__(self, parent=None):
        super().__init__()
        self.setTabBar(EditableTabBar(self))
        self.tabBar().setSelectionBehaviorOnRemove(self.tabBar().SelectLeftTab)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._close_tab)
        self.setMovable(True)

        self.insertTab(0, DoubleColumnPanel(self), "New Tab 1")
        self.insertTab(1, QWidget(self), ' + ')
        self.tabBar().tabButton(1, QTabBar.RightSide).resize(0, 0)
        self.currentChanged.connect(self._add_tab)

    def _close_tab(self, index):
        self.widget(index).deleteLater()
        self.removeTab(index)

    def _add_tab(self, index):
        if index == self.count() - 1:
            '''last tab was clicked. add tab'''
            self.insertTab(index, DoubleColumnPanel(self),
                           "New Tab {0}".format(index + 1))
            self.setCurrentIndex(index)

    def get_config(self):
        """Get current tab names and what are in each tab."""
        tabs = OrderedDict()
        for i in range(self.count() - 1):
            tab_title = self.tabBar().tabText(i)
            dpanel = self.widget(i)
            tabs[tab_title] = dpanel.get_config()
        return tabs

    def restore_config(self, config):
        """Restore config from `get_config`"""
        # Delete all tabs first
        for index in range(self.count() - 1):
            self.widget(index).deleteLater()
            self.removeTab(index)

        index = 1
        for tab_title, dpanel_config in config.items():
            dpanel = DoubleColumnPanel(self)
            self.insertTab(index, dpanel, tab_title)
            index += 1
            dpanel.restore_config(dpanel_config)

        # Remove the default tab
        self.widget(0).deleteLater()
        self.removeTab(0)


class DoubleColumnPanel(QWidget):
    """Double column panel for holding NodePanels"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initUI()

    def _initUI(self):
        self.setLayout(QHBoxLayout())
        self._leftcol = QVBoxLayout()
        self._rightcol = QVBoxLayout()
        self.layout().addLayout(self._leftcol)
        self._vline = QFrame()
        self._vline.setFrameShape(QFrame.VLine)
        self.layout().addWidget(self._vline)
        self.layout().addLayout(self._rightcol)

        self._left_btn = QPushButton("+")
        self._leftcol.addWidget(self._left_btn)
        self._left_btn.clicked.connect(self._add_panel_left)
        self._leftcol.addStretch()

        self._right_btn = QPushButton("+")
        self._rightcol.addWidget(self._right_btn)
        self._right_btn.clicked.connect(self._add_panel_right)
        self._rightcol.addStretch()

    def _add_panel_left(self):
        index = self._leftcol.count()
        self._leftcol.insertWidget(index - 2, NodePanel())

    def _add_panel_right(self):
        index = self._rightcol.count()
        self._rightcol.insertWidget(index - 2, NodePanel())

    def get_config(self):
        """Get what are in each column."""
        left_col = OrderedDict()
        for i in range(self._leftcol.count() - 2):
            node_panel = self._leftcol.itemAt(i).widget()
            left_col[node_panel.get_ip()] = node_panel.get_title()
        right_col = OrderedDict()
        for i in range(self._rightcol.count() - 2):
            node_panel = self._rightcol.itemAt(i).widget()
            right_col[node_panel.get_ip()] = node_panel.get_title()
        return left_col, right_col

    def restore_config(self, config):
        """Restore config from `get_config`"""
        left_col, right_col = config
        for ip, title in left_col.items():
            index = self._leftcol.count()
            node_panel = NodePanel()
            self._leftcol.insertWidget(index - 2, node_panel)
            node_panel.set_ip(ip)
            node_panel.set_title(title)
        for ip, title in right_col.items():
            index = self._rightcol.count()
            node_panel = NodePanel()
            self._rightcol.insertWidget(index - 2, node_panel)
            node_panel.set_ip(ip)
            node_panel.set_title(title)


class ControlPanel(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        self._config_file = os.path.join(pdir, "config.json")
        self._initUI()

    def _initUI(self):
        self.showMaximized()
        self.setWindowTitle("Smartlink Control Panel")
        self.setCentralWidget(EditableTabWidget(self))
        self._load_config()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._save_config)
        self._timer.start(10000)
        #toolbar = self.addToolBar('Open')

    def _save_config(self):
        config = self.centralWidget().get_config()
        try:
            with open(self._config_file, 'w', encoding='ascii') as f:
                json.dump(config, f, indent=2)
            self.statusBar().showMessage("Successfully saved configuration file.")
        except OSError:
            self.statusBar().showMessage(
                "Failed to save configuration file: {filename}".format(filename=self._config_file))

    def _load_config(self):
        try:
            with open(self._config_file, 'r', encoding='ascii') as f:
                config = json.load(f, object_pairs_hook=OrderedDict)
            self.centralWidget().restore_config(config)
        except (OSError, json.JSONDecodeError):
            # file does not exist or corrupted
            self.statusBar().showMessage("Failed to load configuration file.")
        except Exception as err:
            self.statusBar().showMessage(
                "Unexpected error while loading configuration file: {exc}".format(exc=str(err)))


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.setStyle(QStyleFactory.create("fusion"))
    panel = ControlPanel()
    panel.show()

    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
