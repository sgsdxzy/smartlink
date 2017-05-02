import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2, qtpanel

class ControlPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

        self.socket = QTcpSocket()
        socket = self.socket
        socket.connectToHost("127.0.0.1", 5362)

        socket.readyRead.connect(self.parseNode)


    def initUI(self):
        #using a grid layout Qwidget as centeralwidget
        self.centeralwidget = QWidget()
        self.setCentralWidget(self.centeralwidget)
        self.grid = QGridLayout()
        grid = self.grid
        self.centeralwidget.setLayout(grid)

        self.testX = QFrame()
        testX = self.testX
        grid.addWidget(testX, 0, 0)
        testX.setLineWidth(2)
        testX.grid = QGridLayout()
        testX.setLayout(testX.grid)
        testX.grid.addWidget(QLabel("X"), 0, 0)
        testX.current = QLineEdit()
        testX.current.setDisabled(True)
        testX.new = QLineEdit()
        testX.movebutton = QPushButton("Moveto")
        testX.movebutton.clicked.connect(self.sendData)
        testX.grid.addWidget(testX.current, 0, 1)
        testX.grid.addWidget(testX.new, 0, 2)
        testX.grid.addWidget(testX.movebutton, 0, 3)

        self.setWindowTitle('Smartlink Control Panel')
        #self.setWindowIcon(QIcon(iconPath('ppdd.png')))

    def sendData(self):
        op = link_pb2.NodeLink()
        devlink = op.devLink.add()
        devlink.devName = "X"
        link = devlink.link.add()
        link.name = "MOVE"
        link.args.append(self.testX.new.text())
        print(len(op.SerializeToString()))
        self.socket.write(op.SerializeToString())

    def getUpdate(self):
        try:
            nodeupdate = link_pb2.NodeLink.FromString(self.socket.read(1024))
            self.testX.current.setText(nodeupdate.devLink[0].link[0].args[0])
        except:
            #pass
            raise

    def parseNode(self):
        nodeDescription = link_pb2.NodeLink.FromString(self.socket.read(1024))
        print(nodeDescription)
        self.socket.readyRead.disconnect(self.parseNode)
        self.socket.readyRead.connect(self.getUpdate)
        self.socket.write("RDY".encode("utf-8"))


def main():
    app = QApplication(sys.argv)
    panel = qtpanel.NodePanel()
    panel.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
