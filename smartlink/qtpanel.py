from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2
from smartlink.widgets import *

class DevicePanel(QGroupBox):
    """A subpanel to display device status and receive control from user. It is
        generated automatically according to thedescription link desc_link.
        maxlen is the maximum number of basic QWidgets on a single line.
        """
    def __init__(self, node, desc_link, maxlen=20):
        super().__init__()
        self.node = node
        self.desc_link = desc_link
        self.maxlen = maxlen
        self.ctrl_op_list = []
        self.node_op_list = []

        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.row_list = [QHBoxLayout()]
        self.layout.addLayout(self.row_list[-1])
        self.col_index = 0
        self.setFont(self.node.dev_title_font)

    def generate_panel(self):
        """Populate the panel by the description device link dev_link.
            Returns: None
            """
        self.setTitle(self.desc_link.device_name)
        for link in self.desc_link.links:
            widget = OperationWidget(self, link)
            if link.target == link_pb2.Link.CONTROL:
                self.ctrl_op_list.append(widget)
            else: # link.target == link_pb2.Link.NODE:
                self.node_op_list.append(widget)
            self.append_widget(widget)
        self.row_list[-1].addStretch(1)

    def exec_dev_link(self, dev_link):
        """Execute device link on control. This is usually an status update.
            Returns: None
            """
        for link in dev_link.links:
            widget = self.ctrl_op_list[link.id]
            widget.exec_link(link)

    def append_widget(self, widget):
        """Append the OperationWidget to the end of current row. If after the
            operation the number of columns exceeds the maxlen,
            they will be added to the start of a new row.
            Returns: None
            """
        if self.col_index + len(widget) > self.maxlen:
            self.row_list[-1].addStretch(1)
            self.row_list.append(QHBoxLayout())
            self.layout.addLayout(self.row_list[-1])
            self.col_index = 0
        self.row_list[-1].addWidget(widget)
        self.col_index += len(widget)


class OperationWidget(QFrame):
    """A widget to handle a link operation."""
    ctrl_widget_dict = {
        "str": CtrlStrWidget,
        "float": CtrlFloatWidget,
        "bool": CtrlBoolWidget,
        }
    node_widget_dict = {
        "str": NodeStrWidget,
        "float": NodeFloatWidget,
    }

    def __init__(self, device, desc_link):
        super().__init__()
        self.setFrameStyle(QFrame.StyledPanel|QFrame.Plain)
        self.setLineWidth(1)
        self.device = device
        self.desc_link = desc_link
        self.exec_widget_list = []
        self.all_widget_list = []

        self.setFont(self.device.node.default_font)
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.generate()

    def __len__(self):
        return len(self.all_widget_list)

    def generate(self):
        """Parse link.desc and generate corresponding widgets. Link.desc should
            describe the signature of operation. desc is a string containing
            arbitrary number of types separated by single space. Depending on
            whether the operation is on control or node, different widgets are
            generated for operation argument types.
            Currently the following types are implemented for control operation:
                #int : a CtrlIntWidget
                float : a CtrlFloatWidget
                #bool : a CtrlBoolWidget
                str : a CtrlStrWidget
            The following types are implemented for node operation:
                #int : a NodeIntWidget
                float : a NodeFloatWidget
                #bool : a NodeBoolWidget
                str : a NodeStrWidget
            Control operation widgets should implement `exec_arg(str)` to
            execute a control operation. Node operation widgets should implement
             `str get_arg()` to get args for node operation.
            link.args[i] is passed to i-th widget's __init__ as extra args.

            Returns: None
            """
        arg_type_list = self.desc_link.desc.split()
        if self.desc_link.target == link_pb2.Link.CONTROL:
            label = QLabel(self.desc_link.name)
            self.all_widget_list.append(label)
            if len(self.desc_link.args) >= len(arg_type_list):
                for i in range(len(arg_type_list)):
                    arg_type = arg_type_list[i]
                    ext_args = self.desc_link.args[i]
                    widget = self.ctrl_widget_dict.get(arg_type, StrWidget)(ext_args)
                    self.exec_widget_list.append(widget)
                    self.all_widget_list.append(widget)
            else:
                for i in range(len(arg_type_list)):
                    arg_type = arg_type_list[i]
                    widget = self.ctrl_widget_dict.get(arg_type, StrWidget)()
                    self.exec_widget_list.append(widget)
                    self.all_widget_list.append(widget)

        else: # self.desc_link.target == link_pb2.Link.NODE:
            if len(arg_type_list) != 0:
                label = QLabel(self.desc_link.name)
                self.all_widget_list.append(label)
                if len(self.desc_link.args) >= len(arg_type_list):
                    for i in range(len(arg_type_list)):
                        arg_type = arg_type_list[i]
                        ext_args = self.desc_link.args[i]
                        widget = self.node_widget_dict.get(arg_type, StrWidget)(ext_args)
                        self.exec_widget_list.append(widget)
                        self.all_widget_list.append(widget)
                else:
                    for i in range(len(arg_type_list)):
                        arg_type = arg_type_list[i]
                        widget = self.node_widget_dict.get(arg_type, StrWidget)()
                        self.exec_widget_list.append(widget)
                        self.all_widget_list.append(widget)

                button = QPushButton("Apply")
                button.clicked.connect(self.uplink)
                self.all_widget_list.append(button)

            else: # No operation argument require, generate a single button with name
                button = QPushButton(self.desc_link.name)
                button.clicked.connect(self.uplink)
                self.all_widget_list.append(button)

        for widget in self.all_widget_list:
            self.layout.addWidget(widget)

    def exec_link(self, link):
        """Execute link on control.
            Returns: None
            """
        for i in range(len(self.exec_widget_list)):
            self.exec_widget_list[i].exec_arg(link.args[i])

    def get_link(self, dev_link):
        """Collect args from widgets and wrap them into a link, then append it
            to DeviceLink dev_link.
            Returns: the created link_pb2.Link
            """
        link = dev_link.links.add()
        link.id = self.desc_link.id
        for widget in self.exec_widget_list:
            link.args.append(str(widget.get_arg()))
        return link

    @pyqtSlot()
    def uplink(self):
        """Send control link to node server.
            Returns: None
            """
        node_link = link_pb2.NodeLink()
        dev_link = node_link.device_links.add()
        dev_link.device_id = self.device.desc_link.device_id
        self.get_link(dev_link)
        self.device.node.socket.write(node_link.SerializeToString())


class NodePanel(QFrame):
    """A panel to display node status and send controls to node. It is
        generated automatically according to the first description link received
        from socket.
        """
    StyleDisabled = "QPushButton { background-color : #808080}"
    StyleWorking = "QPushButton { background-color : #00FFFF}"
    StyleReady = "QPushButton { background-color : #00FF00}"
    StyleError = "QPushButton { background-color : #FF0000}"
    def __init__(self):
        super().__init__()
        self.ready = False
        self.host_ip = None
        self.socket = QTcpSocket()
        self.desc_link = None
        self.device_list = []
        self.initUI()

    def initUI(self):
        self.setFrameStyle(QFrame.Panel|QFrame.Raised)
        self.setLineWidth(2)

        self.grid_layout = QGridLayout()
        self.grid_layout.setColumnStretch(0, 0)
        self.grid_layout.setColumnStretch(1, 0)
        self.grid_layout.setColumnStretch(2, 1)
        self.setLayout(self.grid_layout)
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setMinimumWidth(100)
        self.grid_layout.addWidget(self.host_edit, 0, 0)
        self.status_light = QPushButton()
        self.status_light.setStyleSheet(self.StyleDisabled)
        self.status_light.setFixedSize(24, 24)
        self.grid_layout.addWidget(self.status_light, 0, 1)
        self.title_font = QFont()
        self.title_font.setWeight(QFont.Black)
        self.title_font.setPointSize(16)
        self.dev_title_font = QFont()
        self.dev_title_font.setWeight(QFont.Bold)
        self.dev_title_font.setPointSize(12)
        self.default_font = QFont()
        self.default_font.setWeight(QFont.Normal)
        self.default_font.setPointSize(10)
        #self.setFont(self.default_font)
        self.title = QLabel("Not connected")
        self.title.setFont(self.title_font)
        self.title.setAlignment(Qt.AlignCenter)
        self.grid_layout.addWidget(self.title, 0, 2)
        self.status_bar = QStatusBar()
        self.grid_layout.addWidget(self.status_bar, 5, 0, 1, 4)
        self.connect_btn = QPushButton("Connect")
        self.reconnect_btn = QPushButton("Reconnect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(24, 24)
        self.grid_layout.addWidget(self.connect_btn, 1, 0,)
        self.grid_layout.addWidget(self.reconnect_btn, 2, 0)
        self.grid_layout.addWidget(self.disconnect_btn, 3, 0)
        self.grid_layout.addWidget(self.close_btn, 0, 3, 1, 2)
        self.dev_layout = QVBoxLayout()
        self.grid_layout.addLayout(self.dev_layout, 1, 1, 4, 3)

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
        while self.dev_layout.count():
            child = self.dev_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def generate_panel(self):
        """Populate the panel by the description node link.
            Returns: None
            """
        self.title.setText(self.desc_link.node_name)
        for dev_link in self.desc_link.device_links:
            device =  DevicePanel(self, dev_link)
            device.generate_panel()
            self.device_list.append(device)
            self.dev_layout.addWidget(device)

    @pyqtSlot()
    def connect(self):
        if self.socket.state() == QAbstractSocket.UnconnectedState: # Not already connected
            self.clear_devices()
            self.host_ip = self.host_edit.text()
            self.status_bar.showMessage("Connecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.error.connect(self.connection_error)
            self.socket.readyRead.connect(self.connection_made)
            self.socket.connectToHost(self.host_ip, 5362)

    @pyqtSlot()
    def disconnect(self):
        if self.socket.state() != QAbstractSocket.UnconnectedState:
            self.reset_socket_slots()
            self.ready = False
            self.status_bar.showMessage("Disconnecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.disconnected.connect(self.connection_closed)
            self.socket.close()

    @pyqtSlot()
    def reconnect(self):
        if self.socket.state() == QAbstractSocket.ConnectedState:
            self.clear_devices()
            self.reset_socket_slots()
            self.ready = False
            self.status_bar.showMessage("Disconnecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            self.socket.disconnected.connect(self.connection_restart)
            self.socket.disconnectFromHost()

    @pyqtSlot()
    def connection_made(self):
        """Executed after connection to host is made"""
        self.status_bar.showMessage("Connected")
        try:
            node_link = link_pb2.NodeLink.FromString(self.socket.read(self.socket.bytesAvailable()))
        except:
            # Didn't receive a valid node description link
            return
        self.desc_link = node_link
        self.generate_panel()

        self.socket.readyRead.disconnect(self.connection_made)
        self.socket.readyRead.connect(self.exec_node_link)
        self.status_light.setStyleSheet(self.StyleReady)
        self.ready = True
        self.status_bar.showMessage("Ready")
        self.socket.write("RDY".encode("utf-8"))

    @pyqtSlot()
    def light_flash(self):
        if self.ready:
            self.status_light.setStyleSheet(self.StyleReady)

    @pyqtSlot()
    def connection_closed(self):
        """Executed after connection is purposely closed."""
        self.status_bar.showMessage("Disconnected")
        self.socket.disconnected.disconnect()
        self.status_light.setStyleSheet(self.StyleDisabled)

    @pyqtSlot()
    def connection_restart(self):
        """Executed when disconnected from host after reconnect() is issued."""
        self.socket.disconnected.disconnect()
        self.status_bar.showMessage("Reconnecting")
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
        # A flashing light effect
        self.status_light.setStyleSheet(self.StyleWorking)

        for dev_link in node_link.device_links:
            device = self.device_list[dev_link.device_id]
            device.exec_dev_link(dev_link)

        QTimer.singleShot(100, self.light_flash)

    @pyqtSlot(QAbstractSocket.SocketError)
    def connection_error(self, error):
        self.reset_socket_slots()
        self.ready = False
        self.status_bar.showMessage(self.socket.errorString())
        self.status_light.setStyleSheet(self.StyleError)
