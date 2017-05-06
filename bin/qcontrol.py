import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2
from smartlink.qtpanel import NodePanel

class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Smartlink Control Panel")

        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.left = QVBoxLayout()
        self.right = QVBoxLayout()
        self.layout.addLayout(self.left)
        self.layout.addLayout(self.right)

        self.left.addWidget(NodePanel())
        self.left.addStretch()
        self.left.addWidget(NodePanel())
        self.left.addStretch()

        self.right.addWidget(NodePanel())
        self.right.addStretch()
        self.right.addWidget(NodePanel())
        self.right.addStretch()


def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("windows"))
    panel = ControlPanel()
    panel.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
