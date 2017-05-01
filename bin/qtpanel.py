import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2, uibuilder

class DevicePanel(QWidget):
    """A subpanel to display device status and get control user input. It
        generates display and input widgets according to description device link
        desc_link.
        """
    def __init__(self, desc_link):
        super().__init__()
        self.desc_link = desc_link
        self.ctrl_funcs = []
        self.node_funcs = []

        self.initUI()

    def initUI(self):
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        widget_index = 0
        self.name_label = QLabel(self.desc_link.device_name)
        self.grid.addWidget(self.name_label, 0, widget_index)
        widget_index += 1
        for link in self.desc_link.links:
            if link.target == link_pb2.Link.CONTROL:
                if link.desc == "num":
                    label = QLabel(link.name)
                    line_edit = QLineEdit()
                    self.grid.addWidget(label, 0, widget_index)
                    widget_index += 1
                    self.grid.addWidget(line_edit, 0, widget_index)
                    widget_index += 1
                    func = lambda args: line_edit.setText(args[0])
                    self.ctrl_funcs.append(func)

    def exec_dev_link(self, dev_link):
        for link in dev_link.links:
            func = self.ctrl_funcs[link.id]
            func(link.args)

class NodePanel(QFrame):
    """A subpanel to display node status and send controls to node. It is
        generated automatically according to the first description link received
        from socket.
        """
    StyleDisabled = "QLabel { background-color : #808080}"
    StyleWorking = "QLabel { background-color : #00FFFF}"
    StyleReady = "QLabel { background-color : #00FF00}"
    StyleError = "QLabel { background-color : #FF0000}"
    def __init__(self):
        super().__init__()
        self.host_ip = None
        self.socket = QTcpSocket()
        self.device_list = []
        self.initUI()

    def initUI(self):
        self.setFrameStyle(QFrame.Box|QFrame.Raised)
        self.setLineWidth(2)

        self.frame_grid = QGridLayout()
        self.frame_grid.setColumnStretch(0, 0)
        self.frame_grid.setColumnStretch(1, 0)
        self.frame_grid.setColumnStretch(2, 1)
        self.setLayout(self.frame_grid)
        self.host_edit = QLineEdit("127.0.0.1")
        self.frame_grid.addWidget(self.host_edit, 0, 0)
        self.status_light = QLabel()
        self.status_light.setStyleSheet(self.StyleDisabled)
        self.status_light.setFixedSize(24, 24)
        self.frame_grid.addWidget(self.status_light, 0, 1)
        self.title = QLabel("Not connected to node")
        self.title.setAlignment(Qt.AlignCenter)
        #self.title.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        self.frame_grid.addWidget(self.title, 0, 2)
        self.connect_btn = QPushButton("Connect")
        self.reconnect_btn = QPushButton("Reconnect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.frame_grid.addWidget(self.connect_btn, 1, 0, 1, 2)
        self.frame_grid.addWidget(self.reconnect_btn, 2, 0, 1, 2)
        self.frame_grid.addWidget(self.disconnect_btn, 3, 0, 1, 2)
        self.node_grid = QGridLayout()
        self.frame_grid.addLayout(self.node_grid, 1, 2, 3, 1)

        self.connect_btn.clicked.connect(self.connect)
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.reconnect_btn.clicked.connect(self.reconnect)

    def connect(self):
        if self.socket.state() == QAbstractSocket.UnconnectedState: # Not already connected
            self.clear_devices()
            self.host_ip = self.host_edit.text()
            self.title.setText("Connecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.error.connect(self.connection_error)
            self.socket.readyRead.connect(self.connection_made)
            self.socket.connectToHost(self.host_ip, 5362)

    def disconnect(self):
        if self.socket.state() != QAbstractSocket.UnconnectedState:
            self.clear_devices()
            self.reset_socket_slots()
            self.title.setText("Disconnecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.disconnected.connect(self.connection_closed)
            self.socket.close()

    def reconnect(self):
        if self.socket.state() == QAbstractSocket.ConnectedState:
            self.clear_devices()
            self.reset_socket_slots()
            self.title.setText("Disconnecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.disconnected.connect(self.connection_restart)
            self.socket.disconnectFromHost()

    def reset_socket_slots(self):
        """Disconnect all slots of self.socket"""
        self.socket.readyRead.disconnect()
        self.socket.error.disconnect()

    def clear_devices(self):
        """Remove all devices from node."""
        self.device_list.clear()
        while self.node_grid.count():
            child = self.node_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def connection_made(self):
        """Executed after connection to host is made"""
        try:
            node_link = link_pb2.NodeLink.FromString(self.socket.read(self.socket.bytesAvailable()))
        except:
            # Didn't receive a valid node description link
            self.indicate_error()
            return
        self.status_light.setStyleSheet(self.StyleReady)
        self.title.setText(node_link.node_name)

        dev_index = 0
        for dev_link in node_link.device_links:
            device = DevicePanel(dev_link)
            self.device_list.append(device)
            self.node_grid.addWidget(device, dev_index, 0)
            dev_index += 1

        self.socket.readyRead.disconnect(self.connection_made)
        self.socket.readyRead.connect(self.exec_node_link)
        self.socket.write("RDY".encode("utf-8"))

    def connection_closed(self):
        """Executed after connection is purposely closed."""
        self.socket.disconnected.disconnect()
        self.title.setText("Not connected to node")
        self.status_light.setStyleSheet(self.StyleDisabled)

    def connection_restart(self):
        """Executed when disconnected from host after reconnect() is issued."""
        self.socket.disconnected.disconnect()
        self.title.setText("Reconnecting")
        self.status_light.setStyleSheet(self.StyleWorking)
        self.socket.error.connect(self.connection_error)
        self.socket.readyRead.connect(self.connection_made)
        self.socket.connectToHost(self.host_ip, 5362)

    def exec_node_link(self):
        try:
            node_link = link_pb2.NodeLink.FromString(self.socket.read(self.socket.bytesAvailable()))
        except:
            # Didn't receive a valid node link
            self.status_light.setStyleSheet(self.StyleError)
            return
        for dev_link in node_link.device_links:
            device = self.device_list[dev_link.device_id]
            device.exec_dev_link(dev_link)

    def connection_error(self):
        self.reset_socket_slots()
        self.title.setText("Connection Error")
        self.status_light.setStyleSheet(self.StyleError)


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
    panel = NodePanel()
    panel.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
