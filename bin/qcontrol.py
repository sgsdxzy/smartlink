import sys
import asyncio
import json

from PyQt5.QtCore import Qt, QEvent
# from PyQt5.QtGui import
from PyQt5.QtWidgets import (QTabBar, QTabWidget, QApplication, QLineEdit,
    QWidget, QStyleFactory, QHBoxLayout, QVBoxLayout, QMainWindow, QPushButton,
    QFrame)

from quamash import QEventLoop
from smartlink import link_pb2
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
        self.removeTab(index)

    def _add_tab(self, index):
        if index == self.count() - 1:
            '''last tab was clicked. add tab'''
            self.insertTab(index, DoubleColumnPanel(self),
                           "New Tab {0}".format(index + 1))
            self.setCurrentIndex(index)

    def get_config(self):
        """Get current tab names and what are in each tab."""
        tabs = []
        for i in range(self.count()-1):
            tab_title = self.tabBar().tabText(i)
            dpanel = self.widget(i)
            tabs.append((tab_title, dpanel.get_config()))

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
        self._leftcol.insertWidget(index-2, NodePanel())

    def _add_panel_right(self):
        index = self._rightcol.count()
        self._rightcol.insertWidget(index-2, NodePanel())

    def get_config(self):
        """Get what are in each column."""
        left_col = []
        for i in range(self._leftcol.count()-2):
            node_panel = self._leftcol.itemAt(i)
            left_col.append((node_panel.get_ip(), node_panel.get_title()))
        right_col = []
        for i in range(self._rightcol.count()-2):
            node_panel = self._rightcol.itemAt(i)
            right_col.append((node_panel.get_ip(), node_panel.get_title()))
        return left_col, right_col


class ControlPanel(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._initUI()

    def _initUI(self):
        self.showMaximized()
        self.setWindowTitle("Smartlink Control Panel")
        self.setCentralWidget(EditableTabWidget(self))
        toolbar = self.addToolBar('Open')


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
