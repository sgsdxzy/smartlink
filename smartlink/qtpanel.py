from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2

class NodeGrid(QGridLayout):
    """A NodeGrid is a QGridLayout to hold operation Widgets. Use add_device_panel
        to add DevicePanels and use them to populate the layout.
        """
    def __init__(self, node_panel, maxlen=20):
        """maxlen is the maximum number of QWidgets a row should hold."""
        super().__init__()
        self.node = node_panel
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
        device_panel = DevicePanel(self, self.node, dev_link)
        return device_panel


class DevicePanel:
    """DevicePanel is in fact not a QWidget. It manages and append actual QWidgets
        to a NodeGrid to ensure alignment across widgets of different devices."""
    def __init__(self, node_grid, node_panel, desc_link):
        self.grid = node_grid
        self.node = node_panel
        self.name_label = None
        self.desc_link = desc_link
        self.ctrl_op_list = []
        self.node_op_list = []

    def generate_panel(self):
        """Populate the panel by the description device link dev_link.
            Returns: None
            """
        for link in self.desc_link.links:
            widget = OperationWidget(self, link)
            if link.target == link_pb2.Link.CONTROL:
                self.ctrl_op_list.append(widget)
            elif link.target == link_pb2.Link.NODE:
                self.node_op_list.append(widget)
            self.append_widgets(widget.generate_widgets())
        self.add_device_label()

    def exec_dev_link(self, dev_link):
        """Execute device link on control.
            Returns: None
            """
        for link in dev_link.links:
            widget = self.ctrl_op_list[link.id]
            widget.exec_link(link)


    def append_widgets(self, widget_list):
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

    def add_device_label(self):
        """After all of the device's actual widgets are added by append_widgets,
            add a device name label at the start of all rows of the device.
            Returns: None
            """
        label_height = self.grid.row_index - self.grid.row_start + 1
        self.name_label = QLabel(self.desc_link.device_name)
        self.name_label.setFont(self.node.dev_title_font)
        self.grid.addWidget(self.name_label, self.grid.row_start, 0, label_height, 1)


class OperationWidget:
    """OperationWidget is in fact not a QWidget. It manages and append actual
        QWidgets to a DevicePanel to ensure alignment across widgets of
        different devices."""
    def __init__(self, device_panel, desc_link):
        self.dev_panel = device_panel
        self.desc_link = desc_link
        self.exec_widget_list =[]
        self.all_widget_list = []

        self.arg_widget_dict = {
            "num": NumWidget,
            "bool": BoolWidget,
            "str": StrWidget}

    def generate_widgets(self):
        """Parse link.desc and generate corresponding widgets. First is a QLabel
            of link.name. link.desc should describe the signature of the concrete
            node function. desc is a string containing arbitrary number of one
            of the following to indicate argument type, separated by single space:
                num : a NumWidget
                bool : a BoolWidget
                str : a StrWidget
            Additional Widgets is generated according to argument type in
            link.desc. These Widgets should implement `exec_arg(str)` to execute a
            control operation and `str get_arg()` to get control arg.
            link.args is passed to __init__ as extra args.
            if an argument type is unknown, an StrWidget is generated.
            If link.target is link_pb2.Link.NODE, a QPushButton is
            appended at the end to send the control command.
            Returns: The generated list of widgets
            """
        arg_type_list = self.desc_link.desc.split()
        if len(arg_type_list) != 0:
            label = QLabel(self.desc_link.name)
            self.all_widget_list.append(label)
            ext_args = self.desc_link.args[:]
            for arg_type in arg_type_list:
                widget = self.arg_widget_dict.get(arg_type, StrWidget)(ext_args)
                self.exec_widget_list.append(widget)
                self.all_widget_list.append(widget)

        if self.desc_link.target == link_pb2.Link.NODE:
            if len(arg_type_list) != 0:
                button = QPushButton("Apply")
            else:
                button = QPushButton(self.desc_link.name)
            button.clicked.connect(self.uplink)
            self.all_widget_list.append(button)
        elif self.desc_link.target == link_pb2.Link.CONTROL:
            pass

        return self.all_widget_list

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
        dev_link.device_id = self.dev_panel.desc_link.device_id
        self.get_link(dev_link)
        self.dev_panel.node.socket.write(node_link.SerializeToString())

class StrWidget(QLineEdit):
    """Widget for handling "str" type argument."""
    def __init__(self, ext_args=None):
        super().__init__(self)
        self.setMinimumWidth(50)

    def exec_arg(self, arg):
        self.setText(arg)

    def get_arg(self):
        return self.text()


class NumWidget(QLineEdit):
    """Widget for handling "num" type argument."""
    def __init__(self, ext_args=None):
        super().__init__("0")
        self.setMinimumWidth(50)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)

    def exec_arg(self, arg):
        self.setText(arg)

    def get_arg(self):
        return self.text()


class BoolWidget(QPushButton):
    """Widget for handling "bool" type argument."""
    StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    StyleDisabled = "QPushButton { color: #FFFFFF; background-color : #808080}"
    def __init__(self, ext_args=None):
        super().__init__("DISABLED")
        self.state = None
        self.setStyleSheet(self.StyleDisabled)

    def exec_arg(self, arg):
        if arg in ["1", "T", "True", "Y", "t", "true"]:
            self.setStyleSheet(self.StyleTrue)
            self.setText("ON")
            self.state = True
        else:
            self.setStyleSheet(self.StyleFalse)
            self.setText("OFF")
            self.state = False

    def get_arg(self):
        if self.state:
            return "1"
        else:
            return "0"


class NodePanel(QFrame):
    """A subpanel to display node status and send controls to node. It is
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
        self.host_edit.setMinimumWidth(120)
        self.frame_grid.addWidget(self.host_edit, 0, 0)
        self.status_light = QPushButton()
        self.status_light.setStyleSheet(self.StyleDisabled)
        self.status_light.setFixedSize(24, 24)
        self.frame_grid.addWidget(self.status_light, 0, 1)
        self.title_font = QFont()
        self.title_font.setWeight(QFont.Black)
        self.title_font.setPointSize(16)
        self.dev_title_font = QFont()
        self.dev_title_font.setWeight(QFont.Bold)
        self.dev_title_font.setPointSize(14)
        self.title = QLabel("Not connected")
        self.title.setFont(self.title_font)
        self.title.setAlignment(Qt.AlignCenter)
        self.frame_grid.addWidget(self.title, 0, 2)
        self.status_bar = QStatusBar()
        self.frame_grid.addWidget(self.status_bar, 4, 0, 1, 4)
        self.connect_btn = QPushButton("Connect")
        self.reconnect_btn = QPushButton("Reconnect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(24, 24)
        self.frame_grid.addWidget(self.connect_btn, 1, 0, 1, 2)
        self.frame_grid.addWidget(self.reconnect_btn, 2, 0, 1, 2)
        self.frame_grid.addWidget(self.disconnect_btn, 3, 0, 1, 2)
        self.frame_grid.addWidget(self.close_btn, 0, 3, 1, 2)
        self.node_grid = NodeGrid(self)
        self.frame_grid.addLayout(self.node_grid, 1, 2, 3, 1)

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
        self.ready = True
        self.title.setText(self.desc_link.node_name)

        for dev_link in self.desc_link.device_links:
            device = self.node_grid.add_device_panel(dev_link)
            self.device_list.append(device)
            device.generate_panel()

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
