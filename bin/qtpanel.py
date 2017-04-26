import socket
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

from smartlink import smartlink_pb2 as pb2

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
        testX.setFrameStyle(QFrame.Box | QFrame.Raised)
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
        op = pb2.DeviceOperation()
        op.devicename = "X"
        op.operation = "MOVE"
        op.args.append(self.testX.new.text())
        self.socket.write(op.SerializeToString())

    def getUpdate(self):
        try:
            nodeupdate = pb2.NodeUpdate.FromString(self.socket.read(1024))
            self.testX.current.setText(nodeupdate.updates[0].status[0])
        except:
            #pass
            raise

    def parseNode(self):
        nodeDescription = pb2.NodeDescription.FromString(self.socket.read(1024))
        #print(nodeDescription)
        self.socket.readyRead.disconnect(self.parseNode)
        self.socket.readyRead.connect(self.getUpdate)
        self.socket.write("READY".encode("utf-8"))


def main():
    app = QApplication(sys.argv)
    panel = ControlPanel()
    panel.show()
    sys.exit(app.exec_())
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect the socket to the port where the server is listening
    server_address = ('localhost', 5362)
    sock.connect(server_address)

    while True:
        cmd = input("Operation: ")
        cmd = cmd.split()


if __name__ == '__main__':
    main()
