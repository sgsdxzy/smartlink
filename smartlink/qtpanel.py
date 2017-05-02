from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2

class NodeGrid(QGridLayout):
    """A NodeGrid is a QGridLayout to hold operation Widgets. Use add_device_panel
        to add DevicePanels and use them to populate the layout.
        """
    def __init__(self, maxlen=20):
        """maxlen is the maximum number of QWidgets a row should hold."""
        super().__init__()
        self.maxlen = maxlen
        self.row_index = -1
        self.row_start = -1 # The staring row of current DevicePanel on NodeGrid
        self.col_index = 1

    def clear_all(self):
        """Remove all DevicePanels and QWidgets.
            Returns: None
            """
        while self.count():
            child = self.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.row_index = -1
        self.row_start = -1
        self.col_index = 1

    def add_device_panel(self, dev_link):
        """Append a DevicePanel at the end of rows.
            Returns: DevicePanel
            """
        self.row_index += 1
        self.row_start = self.row_index
        self.col_index = 1
        device_panel = DevicePanel(self, dev_link)
        return device_panel


class DevicePanel:
    """DevicePanel is in fact not a QWidget. It manages and append actual QWidgets
        to a NodeGrid to ensure alignment across widgets of different devices."""
    def __init__(self, node_grid, dev_link):
        self.grid = node_grid
        self.name_label = None
        self.dev_link = dev_link
        self.opwidget_list = []

    def generate_panel(self):
        """Populate the panel by the description device link dev_link.
            Returns: None
            """
        for link in self.dev_link.links:
            opwidget = OperationWidget(self, link)
            self.opwidget_list.append(opwidget)
            opwidget.generate_widgets()
            self._append_widgets(opwidget.widget_list)
        self._add_device_label()

    def _append_widgets(self, widget_list):
        """Append the OperationWidget to the end of current row. If after the
            operation the number of columns exceeds the maxlen of underlying
            NodeGrid, they will be added to the start of a new row.
            Returns: None
            """
        col_length = len(widget_list)
        if self.grid.col_index + col_length > self.grid.maxlen:
            self.grid.row_index += 1
            self.grid.col_index = 1
        for widget in widget_list:
            self.grid.addWidget(widget, self.grid.row_index, self.grid.col_index)
            self.grid.col_index += 1

    def _add_device_label(self):
        """After all of the device's actual widgets are added by append_widgets,
            add a device name label at the start of all rows of the device.
            Returns: None
            """
        label_height = self.grid.row_index - self.grid.row_start + 1
        self.name_label = QLabel(self.dev_link.device_name)
        self.grid.addWidget(self.name_label, self.grid.row_start, 0, label_height, 1)


class OperationWidget:
    """OperationWidget is in fact not a QWidget. It manages and append actual
        QWidgets to a DevicePanel to ensure alignment across widgets of
        different devices."""
    def __init__(self, device_panel, link):
        self.panel = device_panel
        self.link = link
        self.widget_list = []
        self.validator_list = []

    def generate_widgets(self):
        """Parse link.desc and generate corresponding widgets. First is a QLabel
            of link.name. link.desc should describe the signature of the concrete
            node function. desc is a string containing arbitrary number of one
            of the following, separated by single space:
                num : a QLineEdit
                bool : a QPushButton to indicate state
            Additional QWidgets is generated according to link.desc. If
            link.target is link_pb2.Link.NODE, a QPushButton is appended at
            the end to send the control command.
            Returns: None
            """
        label = QLabel(self.link.name)
        self.widget_list.append(label)
        arg_list = self.link.desc.split()
        for arg in arg_list:
            if arg == "num":
                line_edit = QLineEdit()
                self.widget_list.append(line_edit)
                validator = QDoubleValidator()
                self.validator_list.append(validator)
                line_edit.setValidator(validator)
            elif arg == "bool":
                pass
        if self.link.target == link_pb2.Link.CONTROL:
            pass
        elif self.link.target == link_pb2.Link.NODE:
            button = QPushButton("Apply")
            self.widget_list.append(button)


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
        self.node_link = None
        self.initUI()
        self.device_list = []

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
        self.node_grid = NodeGrid()
        self.frame_grid.addLayout(self.node_grid, 1, 2, 4, 1)

        self.connect_btn.clicked.connect(self.connect)
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.reconnect_btn.clicked.connect(self.reconnect)

    def reset_socket_slots(self):
        """Disconnect all slots of self.socket
            Returns: None
            """
        self.socket.readyRead.disconnect()
        self.socket.error.disconnect()

    def clear_devices(self):
        """Remove all devices from node.
            Returns: None
            """
        self.device_list.clear()
        self.node_grid.clear_all()

    def generate_panel(self):
        """Populate the panel by the description node link.
            Returns: None
            """
        self.status_light.setStyleSheet(self.StyleReady)
        self.title.setText(self.node_link.node_name)

        for dev_link in self.node_link.device_links:
            device = self.node_grid.add_device_panel(dev_link)
            self.device_list.append(device)
            device.generate_panel()

    @pyqtSlot()
    def connect(self):
        if self.socket.state() == QAbstractSocket.UnconnectedState: # Not already connected
            self.clear_devices()
            self.host_ip = self.host_edit.text()
            self.title.setText("Connecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.error.connect(self.connection_error)
            self.socket.readyRead.connect(self.connection_made)
            self.socket.connectToHost(self.host_ip, 5362)

    @pyqtSlot()
    def disconnect(self):
        if self.socket.state() != QAbstractSocket.UnconnectedState:
            self.clear_devices()
            self.reset_socket_slots()
            self.title.setText("Disconnecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.disconnected.connect(self.connection_closed)
            self.socket.close()

    @pyqtSlot()
    def reconnect(self):
        if self.socket.state() == QAbstractSocket.ConnectedState:
            self.clear_devices()
            self.reset_socket_slots()
            self.title.setText("Disconnecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.disconnected.connect(self.connection_restart)
            self.socket.disconnectFromHost()

    @pyqtSlot()
    def connection_made(self):
        """Executed after connection to host is made"""
        try:
            node_link = link_pb2.NodeLink.FromString(self.socket.read(self.socket.bytesAvailable()))
        except:
            # Didn't receive a valid node description link
            return
        self.node_link = node_link

        self.generate_panel()

        self.socket.readyRead.disconnect(self.connection_made)
        #self.socket.readyRead.connect(self.exec_node_link)
        self.socket.write("RDY".encode("utf-8"))

    @pyqtSlot()
    def connection_closed(self):
        """Executed after connection is purposely closed."""
        self.socket.disconnected.disconnect()
        self.title.setText("Not connected to node")
        self.status_light.setStyleSheet(self.StyleDisabled)

    @pyqtSlot()
    def connection_restart(self):
        """Executed when disconnected from host after reconnect() is issued."""
        self.socket.disconnected.disconnect()
        self.title.setText("Reconnecting")
        self.status_light.setStyleSheet(self.StyleWorking)
        self.socket.error.connect(self.connection_error)
        self.socket.readyRead.connect(self.connection_made)
        self.socket.connectToHost(self.host_ip, 5362)

    @pyqtSlot()
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

    @pyqtSlot(QAbstractSocket.SocketError)
    def connection_error(self, error):
        self.reset_socket_slots()
        self.title.setText(self.socket.errorString())
        self.status_light.setStyleSheet(self.StyleError)


class NumExec:
    def __init__(self, op_id, dev_id, line_edit, button, node):
        self.op_id = op_id
        self.dev_id = dev_id
        self.le = line_edit
        self.btn = button
        self.node = node

    def slot_exec(self):
        node_link = link_pb2.NodeLink()
        dev_link = node_link.device_links.add()
        dev_link.device_id = self.dev_id
        link = dev_link.links.add()
        link.id = self.op_id
        link.args.append(self.le.text())

        str_link = node_link.SerializeToString()
        self.node.socket.write(str_link)
