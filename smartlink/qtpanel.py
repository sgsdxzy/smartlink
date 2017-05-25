import asyncio
from asyncio import ensure_future

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from google.protobuf.message import DecodeError

from quamash import QEventLoop
from smartlink import EndOfStreamError, ProtocalError, StreamReadWriter
from smartlink import link_pb2, varint
from smartlink.widgets import *


class CommandWidget(QFrame):
    """A widget to handle user commands."""
    widget_dict = {
        "str": CStrWidget,
        "float": CFloatWidget,
    }
    StyleNormal = "CommandWidget { border: 1px solid #CCCCCC; }"
    StyleError = "CommandWidget { border: 1px solid #FF0000; }"

    def __init__(self, grp, desc_link):
        super().__init__()
        self.grp = grp
        self.desc_link = desc_link
        self.widget_list = []
        self.full_widget_list = []

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self.StyleNormal)
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.generate_UI()

    def __len__(self):
        return len(self.full_widget_list)

    def generate_UI(self):
        """Parse link.sig and generate corresponding widgets. link.sig should
        describe the signature of command. sig is a string containing
        arbitrary number of types separated by single space.
        Currently the following types are implemented for command:
            #int : a CIntWidget
            float : a CFloatWidget
            #bool : a CBoolWidget
            str : a CStrWidget
        These command widgets should implement `str get_cmd()` to get arguments.
        An empty string means invalid input. link.data is slited by ';', and
        n-th substring is passed to i-th widget's __init__ as extra args.

        Returns: None
        """
        if self.desc_link.sig:
            sig_list = self.desc_link.sig.split(';')
            arg_list = self.desc_link.data.split(';')
            label = QLabel(self.desc_link.name)
            self.full_widget_list.append(label)
            if len(arg_list) >= len(sig_list):
                for i in range(len(sig_list)):
                    sig = sig_list[i]
                    ext_args = arg_list[i]
                    widget = self.widget_dict.get(sig, CStrWidget)(ext_args)
                    self.widget_list.append(widget)
                    self.full_widget_list.append(widget)
            else:
                for i in range(len(sig_list)):
                    sig = sig_list[i]
                    widget = self.widget_dict.get(sig, CStrWidget)()
                    self.widget_list.append(widget)
                    self.full_widget_list.append(widget)
            button = QPushButton("Apply")
            button.clicked.connect(self.send_command)
            self.full_widget_list.append(button)

        else:  # signature is empty, generate a single button with name
            button = QPushButton(self.desc_link.name)
            button.clicked.connect(self.send_command)
            self.full_widget_list.append(button)

        for widget in self.full_widget_list:
            self.layout.addWidget(widget)

    def get_link(self, grp_link):
        """Collect args from widgets and wrap them into a link, then append it
        to GroupLink grp_link.

        Returns: the created link_pb2.Link or None if not valid
        """
        cmds = tuple(widget.get_cmd() for widget in self.widget_list)
        if not all(cmds):
            return None
        link = grp_link.links.add()
        link.id = self.desc_link.id
        link.data = ';'.join(cmds)
        return link

    @pyqtSlot()
    def send_command(self):
        """Send command to node server.

        Returns: None
        """
        node_link = link_pb2.NodeLink()
        dev_link = node_link.dev_links.add()
        dev_link.id = self.grp.dev.desc_link.id
        grp_link = dev_link.grp_links.add()
        grp_link.id = self.grp.desc_link.id
        if self.get_link(grp_link):
            self.grp.dev.node.send_command(node_link)


class UpdateWidget(QFrame):
    """A widget to handle updates from node."""
    widget_dict = {
        "str": UStrWidget,
        "float": UFloatWidget,
        "bool": UBoolWidget,
    }
    StyleNormal = "UpdateWidget { border: 1px solid #CCCCCC; }"
    StyleError = "UpdateWidget { border: 1px solid #FF0000; }"

    def __init__(self, grp, desc_link):
        super().__init__()
        self.grp = grp
        self.desc_link = desc_link
        self.widget_list = []
        self.full_widget_list = []

        # self.setObjectName("U");
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self.StyleNormal)
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.generate_UI()

    def __len__(self):
        return len(self.full_widget_list)

    def generate_UI(self):
        """Parse link.sig and generate corresponding widgets. link.sig should
        describe the signature of command. sig is a string containing
        arbitrary number of types separated by single space.
        Currently the following types are implemented for updates:
            #int : a UIntWidget
            float : a UFloatWidget
            bool : a UBoolWidget
            str : a UStrWidget
        These update widgets should implement `update(str)` to update its contents.
        link.data is slited by ';', and n-th substring is passed to i-th
        widget's __init__ as extra args.

        Returns: None
        """
        sig_list = self.desc_link.sig.split(';')
        arg_list = self.desc_link.data.split(';')
        label = QLabel(self.desc_link.name)
        self.full_widget_list.append(label)
        if len(arg_list) >= len(sig_list):
            for i in range(len(sig_list)):
                sig = sig_list[i]
                ext_args = arg_list[i]
                widget = self.widget_dict.get(sig, UStrWidget)(ext_args)
                self.widget_list.append(widget)
                self.full_widget_list.append(widget)
        else:
            for i in range(len(sig_list)):
                sig = sig_list[i]
                widget = self.widget_dict.get(sig, UStrWidget)()
                self.widget_list.append(widget)
                self.full_widget_list.append(widget)

        for widget in self.full_widget_list:
            self.layout.addWidget(widget)

    def update(self, link):
        """Update contents from link.

        Returns: None
        """
        try:
            arg_list = link.data.split(';')
            for i in range(len(arg_list)):
                self.widget_list[i].update(arg_list[i])
            self.setStyleSheet(self.StyleNormal)
        except:
            self.setStyleSheet(self.StyleError)
            self.grp.dev.display_error("Failed to display some update(s)")


class GroupPanel(QFrame):
    """A subpanel to display a group of operations. maxlen is the maximum number
    of basic QWidgets other on a single line.
    """
    StyleNormal = "GroupPanel { border: 1px solid #808080; }"
    StyleError = "GroupPanel { border: 1px solid #FF0000; }"

    def __init__(self, dev, desc_link, maxlen=20):
        super().__init__()
        self.dev = dev
        self.desc_link = desc_link
        self.maxlen = maxlen
        self.commands = []
        self.updates = []

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self.StyleNormal)
        self.outer_layout = QHBoxLayout()
        self.setLayout(self.outer_layout)
        self.layout = QVBoxLayout()
        self.outer_layout.addLayout(self.layout)
        self.row_list = [QHBoxLayout()]
        self.layout.addLayout(self.row_list[-1])
        self.generate_UI()

    def generate_UI(self):
        """Populate the panel by the description device link desc_link.

        Returns: None
        """
        if self.desc_link.name != "":
            self.label = QLabel(self.desc_link.name)
            self.label.setFont(self.dev.node.grp_title_font)
            # self.label.setFrameStyle(QFrame.StyledPanel|QFrame.Plain)
            # self.label.setLineWidth(0.5)
            self.outer_layout.insertWidget(0, self.label)

        col_index = 0
        for link in self.desc_link.links:
            if link.type == link_pb2.Link.COMMAND:
                widget = CommandWidget(self, link)
                self.commands.append(widget)
            else:  # link.type == link_pb2.Link.UPDATE:
                widget = UpdateWidget(self, link)
                self.updates.append(widget)

            if col_index + len(widget) > self.maxlen:
                self.row_list[-1].addStretch(1)
                self.row_list.append(QHBoxLayout())
                self.layout.addLayout(self.row_list[-1])
                col_index = 0
            self.row_list[-1].addWidget(widget)
            col_index += len(widget)
        self.row_list[-1].addStretch(1)

    def update(self, grp_link):
        """Update contents accroding to grp_link

        Returns: None
        """
        for link in grp_link.links:
            widget = self.updates[link.id]
            widget.update(link)


class DevicePanel(QWidget):
    """A subpanel to display device status and commands. It is
    generated automatically according to the description link desc_link.
    """

    def __init__(self, node, desc_link):
        super().__init__()
        self.node = node
        self.desc_link = desc_link
        self.groups = []

        # Draw a frame
        self.outer_layout = QGridLayout()
        self.setLayout(self.outer_layout)
        self.outer_layout.addWidget(QVLine(), 0, 0, 3, 1)
        self.outer_layout.addWidget(QVLine(), 0, 3, 3, 1)
        self.outer_layout.addWidget(QHLine(), 0, 2, 1, 2)
        self.outer_layout.addWidget(QHLine(), 2, 0, 1, 4)
        self.headline = QHBoxLayout()
        self.outer_layout.addLayout(self.headline, 0, 1)
        self.layout = QVBoxLayout()
        self.outer_layout.addLayout(self.layout, 1, 1, 1, 2)
        self.generate_UI()

    def generate_UI(self):
        """Populate the panel by desc_link.

        Returns: None
        """
        self.title = QLabel(self.desc_link.name)
        self.title.setFont(self.node.dev_title_font)
        self.headline.addWidget(self.title)
        # TODO: apply all button
        for grp_link in self.desc_link.grp_links:
            grp = GroupPanel(self, grp_link)
            self.groups.append(grp)
            self.layout.addWidget(grp)

    def update(self, dev_link):
        """Update contents accroding to dev_link.

        Returns: None
        """
        for grp_link in dev_link.grp_links:
            grp = self.groups[grp_link.id]
            grp.update(grp_link)

    def apply_all(self):
        """Send all commands to node.

        Returns: None
        """
        pass

    def display_error(self, msg):
        # TODO
        pass


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
        self._connected = False
        self._host_ip = None
        self._readwriter = None
        self._desc_link = None
        self._devices = []
        self._initUI()

    def _initUI(self):
        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLineWidth(2)

        self.outer_layout = QGridLayout()
        self.outer_layout.setColumnStretch(0, 0)
        self.outer_layout.setColumnStretch(1, 0)
        self.outer_layout.setColumnStretch(2, 1)
        self.outer_layout.setColumnStretch(3, 0)
        self.setLayout(self.outer_layout)
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setMinimumWidth(100)
        self.outer_layout.addWidget(self.host_edit, 0, 0)
        self.status_light = QPushButton()
        self.status_light.setStyleSheet(self.StyleDisabled)
        self.status_light.setFixedSize(24, 24)
        self.outer_layout.addWidget(self.status_light, 0, 1)
        self.title_font = QFont()
        self.title_font.setWeight(QFont.Black)
        self.title_font.setPointSize(18)
        self.dev_title_font = QFont()
        self.dev_title_font.setWeight(QFont.Bold)
        self.dev_title_font.setPointSize(16)
        self.grp_title_font = QFont()
        self.grp_title_font.setWeight(QFont.Bold)
        self.grp_title_font.setPointSize(12)

        self.title = QLabel("Not connected")
        self.title.setFont(self.title_font)
        self.title.setAlignment(Qt.AlignCenter)
        self.outer_layout.addWidget(self.title, 0, 2)
        self.status_bar = QStatusBar()
        self.outer_layout.addWidget(self.status_bar, 5, 0, 1, 4)
        self.connect_btn = QPushButton("Connect")
        self.reconnect_btn = QPushButton("Reconnect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(24, 24)
        self.outer_layout.addWidget(self.connect_btn, 1, 0,)
        self.outer_layout.addWidget(self.reconnect_btn, 2, 0)
        self.outer_layout.addWidget(self.disconnect_btn, 3, 0)
        self.outer_layout.addWidget(self.close_btn, 0, 3, 1, 2)
        self.layout = QVBoxLayout()
        self.outer_layout.addLayout(self.layout, 1, 1, 4, 3)

        self.connect_btn.clicked.connect(self.connect_btn_exec)
        self.disconnect_btn.clicked.connect(self.disconnect_btn_exec)
        self.reconnect_btn.clicked.connect(self.reconnect_btn_exec)
        self.close_btn.clicked.connect(self.close)


    def _clear_devices(self):
        """Remove all device panels from node panel.

        Returns: None
        """
        self._devices.clear()
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _generate_panel(self):
        """Populate the panel by the description node link.

        Returns: None
        """
        self.title.setText(self._desc_link.name)
        for dev_link in self._desc_link.dev_links:
            dev = DevicePanel(self, dev_link)
            self._devices.append(dev)
            self.layout.addWidget(dev)

    def send_command(self, node_link):
        if self._connected:
            bin_link = node_link.SerializeToString()
            self._readwriter.write_bin_link(bin_link)

    @pyqtSlot()
    def connect_btn_exec(self):
        if not self._connected:
            self._clear_devices()
            self._host_ip = self.host_edit.text()
            self.status_bar.showMessage("Connecting")
            self.status_light.setStyleSheet(self.StyleWorking)
            ensure_future(self._connect())

    async def _connect(self):
        """Coroutine to make connection to node server."""
        try:
            reader, writer = await asyncio.open_connection(host=self._host_ip, port=5362)
            self._readwriter = StreamReadWriter(reader, writer)

            #Parse description link from nodeserver
            length = await varint.decode(self._readwriter)
            buf = await self._readwriter.read(length)
            while len(buf) < length:
                buf += await self.read(length-len(buf))
            node_link = link_pb2.NodeLink.FromString(buf)
            self._desc_link = node_link

            self._generate_panel()
            self.status_light.setStyleSheet(self.StyleReady)
            self._connected = True
            self.status_bar.showMessage("Ready")
            self._readwriter.write("RDY".encode("ascii"))
            ensure_future(self._handle_update())
        except Exception as e:
            self._connected = False
            self.status_bar.showMessage(str(e))
            self.status_light.setStyleSheet(self.StyleError)

    async def _handle_update(self):
        try:
            while True:
                #Parse NodeLink
                length = await varint.decode(self._readwriter)
                buf = await self._readwriter.read(length)
                while len(buf) < length:
                    buf += await self.read(length-len(buf))
                update_link = link_pb2.NodeLink.FromString(buf)

                for dev_link in update_link.dev_links:
                    dev = self._devices[dev_link.id]
                    dev.update(dev_link)
                # A flashing light effect
                self.status_light.setStyleSheet(self.StyleWorking)
                QTimer.singleShot(100, self.light_flash)
        except EndOfStreamError:
            #server disconnects
            pass
        except (DecodeError, ProtocalError):
            #purposely drop connection
            self._readwriter.close()
        finally:
            self.status_bar.showMessage("Disconnected")
            self.status_light.setStyleSheet(self.StyleError)

    @pyqtSlot()
    def disconnect_btn_exec(self):
        if self._connected:
            self._readwriter.close()
            self._connected = False
            self.status_bar.showMessage("Disconnected")
            self.status_light.setStyleSheet(self.StyleDisabled)

    @pyqtSlot()
    def reconnect_btn_exec(self):
        if self._connected:
            self._readwriter.close()
            self._connected = False
            self.status_bar.showMessage("Disconnected")
            self.status_light.setStyleSheet(self.StyleDisabled)
            self.connect_btn_exec()

    @pyqtSlot()
    def light_flash(self):
        if self._connected:
            self.status_light.setStyleSheet(self.StyleReady)

    @pyqtSlot()
    def update(self):
        try:
            node_link = link_pb2.NodeLink.FromString(
                self.socket.read(self.socket.bytesAvailable()))
        except:
            # Didn't receive a valid node link
            self.status_light.setStyleSheet(self.StyleError)
            return
        # A flashing light effect
        self.status_light.setStyleSheet(self.StyleWorking)
        for dev_link in node_link.dev_links:
            dev = self._devices[dev_link.id]
            dev.update(dev_link)
        QTimer.singleShot(100, self.light_flash)

    @pyqtSlot()
    def close(self):
        if self._connected:
            self.status_bar.showMessage(
                "Please disconnect before closing panel")
        else:
            self.deleteLater()
