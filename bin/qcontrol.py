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

        self.grid = QGridLayout()
        self.setLayout(self.grid)

        self.grid.addWidget(NodePanel(), 0, 0)
        self.grid.addWidget(NodePanel(), 0, 1)
        self.grid.addWidget(NodePanel(), 1, 0)
        self.grid.addWidget(NodePanel(), 1, 1)



def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("windows"))
    panel = ControlPanel()
    panel.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
