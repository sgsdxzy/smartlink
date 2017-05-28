import os, sys
import base64
import asyncio
from asyncio import ensure_future
from datetime import datetime

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from google.protobuf.message import DecodeError

from smartlink import EndOfStreamError, ProtocalError, StreamReadWriter, link_pb2, varint
from smartlink.widgets import *


class Logger(QTextEdit):
    """A non-persistent object-level logger with a QTextEdit display"""
    _datefmt = '%Y-%m-%d %H:%M:%S'
    _fmt = "[{source}:{level}]\t{asctime}\t{name}:\t{message}\n"

    def __init__(self, datefmt=None, fmt=None):
        super().__init__()
        self._datefmt = datefmt or SimpleLogger.datefmt
        self._fmt = fmt or SimpleLogger.fmt

        self.hide()

    def set_name(self, name):
        self.setWindowTitle(name)

    def info(self, name, message, source="CONTROL"):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="INFO", name=name, message=message)

    def error(self, name, message, source="CONTROL"):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="ERROR", name=name, message=message)

    def exception(self, name, message, source="CONTROL"):
        """Print the message and traceback."""
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="EXCEPTION", name=name, message=message)
        record += traceback.format_exc()

class CommandWidget(QFrame):
    """A widget to handle user commands."""
    _widget_dict = {
        "str": CStrWidget,
        "float": CFloatWidget,
    }
    _StyleNormal = "CommandWidget { border: 1px solid #CCCCCC; }"
    __StyleError = "CommandWidget { border: 1px solid #FF0000; }"

    def __init__(self, grp_panel, desc_link):
        super().__init__()
        self._grp_panel = grp_panel
        self._desc_link = desc_link
        self._name = desc_link.name
        self._fullname = '.'.join((grp_panel._fullname, self._name))
        self._id = desc_link.id
        self._widget_list = []
        self._full_widget_list = []
        self._logger = grp_panel._logger

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self._StyleNormal)
        self._layout = QHBoxLayout()
        self.setLayout(self._layout)
        self._generate_UI()

    @property
    def widget_length(self):
        return len(self._full_widget_list)

    def _generate_UI(self):
        """Parse desc link.sigs and generate corresponding widgets. link.sigs
        is a list describing the signature of command.
        Currently the following types are implemented for command:
            # int : a CIntWidget
            float : a CFloatWidget
            # bool : a CBoolWidget
            str : a CStrWidget
        These command widgets should implement `get_arg() -> str` to
        get arguments. An empty string means invalid input.
        n-th link.args is passed to n-th widget's __init__ as extra arg.

        Returns: None
        """
        try:
            if self._desc_link.sigs:
                label = QLabel(self._desc_link.name)
                self._full_widget_list.append(label)
                for i, sig in enumerate(self._desc_link.sigs):
                    if len(self._desc_link.args) > i:
                        ext_arg = self._desc_link.args[i]
                    else:
                        ext_arg = None
                    widget = self._widget_dict.get(sig, CStrWidget)(ext_arg)
                    self._widget_list.append(widget)
                    self._full_widget_list.append(widget)
                button = QPushButton("Apply")
                button.clicked.connect(self._send_command)
                self._full_widget_list.append(button)

            else:  # signature is empty, generate a single button with name
                button = QPushButton(self._desc_link.name)
                button.clicked.connect(self._send_command)
                self._full_widget_list.append(button)

            for widget in self._full_widget_list:
                self._layout.addWidget(widget)

        except Exception:
            self._logger.exception(self._fullname, "Failed to create widget.")
            raise

    @pyqtSlot()
    def _light_flash(self):
        """A flashing light effect"""
        self.setStyleSheet(self._StyleNormal)

    def get_link(self, grp_link):
        """Collect args from widgets and wrap them into a link, then append it
        to GroupLink grp_link.

        Returns: the created link_pb2.Link or None if invalid
        """
        cmds = tuple(str(widget.get_arg()) for widget in self._widget_list)
        if not all(cmds):
            self.setStyleSheet(self.__StyleError)
            QTimer.singleShot(1000, self._light_flash)
            return None
        else:
            link = grp_link.links.add()
            link.id = self._id
            link.args.extend(cmds)
            return link

    def get_full_link(self, grp_link):
        """Collect args from widgets and wrap them into a link, then append it
        to GroupLink grp_link. This link also contains additional
        information such as the command's name. This is used for restoring
        commands.

        Returns: the created link_pb2.Link or None if invalid
        """
        cmds = tuple(str(widget.get_arg()) for widget in self._widget_list)
        if not (cmds and all(cmds)):
            return None
        else:
            link = grp_link.links.add()
            link.type = link_pb2.Link.COMMAND
            link.id = self._id
            link.name = self._name
            link.sigs.extend(self._desc_link.sigs)
            link.args.extend(cmds)
            return link

    @pyqtSlot()
    def _send_command(self):
        """Send command to nodeserver.

        Returns: None
        """
        node_link = link_pb2.NodeLink()
        dev_link = node_link.dev_links.add()
        dev_link.id = self._grp_panel._devpanel._id
        grp_link = dev_link.grp_links.add()
        grp_link.id = self._grp_panel._id
        if self.get_link(grp_link):
            self._grp_panel._devpanel._nodepanel.send_command(node_link)


class UpdateWidget(QFrame):
    """A widget to handle updates from node."""
    _widget_dict = {
        "str": UStrWidget,
        "float": UFloatWidget,
        "bool": UBoolWidget,
    }
    _StyleNormal = "UpdateWidget { border: 1px solid #CCCCCC; }"
    __StyleError = "UpdateWidget { border: 1px solid #FF0000; }"

    def __init__(self, grp_panel, desc_link):
        super().__init__()
        self._grp_panel = grp_panel
        self._desc_link = desc_link
        self._name = desc_link.name
        self._fullname = '.'.join((grp_panel._fullname, self._name))
        self._id = desc_link.id
        self._widget_list = []
        self._full_widget_list = []
        self._logger = grp_panel._logger

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self._StyleNormal)
        self._layout = QHBoxLayout()
        self.setLayout(self._layout)
        self._generate_UI()

    @property
    def widget_length(self):
        return len(self._full_widget_list)

    def _generate_UI(self):
        """Parse desc link.sigs and generate corresponding widgets. link.sigs
        is a list describing the signature of update.
        Currently the following types are implemented for updates:
            # int : a UIntWidget
            float : a UFloatWidget
            bool : a UBoolWidget
            str : a UStrWidget
        These update widgets should implement `update_from(str)` to update
        its contents. n-th link.args is passed to n-th widget's __init__
        as extra arg.

        Returns: None
        """
        try:
            if self._desc_link.sigs:
                label = QLabel(self._desc_link.name)
                self._full_widget_list.append(label)
                for i, sig in enumerate(self._desc_link.sigs):
                    if len(self._desc_link.args) > i:
                        ext_arg = self._desc_link.args[i]
                    else:
                        ext_arg = None
                    widget = self._widget_dict.get(sig, UStrWidget)(ext_arg)
                    self._widget_list.append(widget)
                    self._full_widget_list.append(widget)

            for widget in self._full_widget_list:
                self._layout.addWidget(widget)
        except Exception:
            self._logger.exception(self._fullname, "Failed to create widget.")
            raise

    @pyqtSlot()
    def _light_flash(self):
        """A flashing light effect"""
        self.setStyleSheet(self._StyleNormal)

    def update_from(self, link):
        """Update contents from link.

        Returns: None
        """
        try:
            for i, arg in enumerate(link.args):
                self._widget_list[i].set_arg(arg)
        except Exception:
            self._logger.exception(self._fullname, "Failed to display update.")
            self.setStyleSheet(self.__StyleError)
            QTimer.singleShot(1000, self._light_flash)

    def get_status(self, grp_link):
        """Collect status args from widgets and wrap them into a link,
        then append it to GroupLink grp_link.

        Returns: the created link_pb2.Link
        """
        link = grp_link.links.add()
        link.type = link_pb2.Link.UPDATE
        link.id = self._id
        link.name = self._name
        link.sigs.extend(self._desc_link.sigs)
        link.args.extend(str(widget.get_arg()) for widget in self._widget_list)
        return link


class GroupPanel(QFrame):
    """A subpanel to display a group of operations. maxlen is the
    maximum number of basic QWidgets on a single line.
    """
    _title_font = QFont()
    _title_font.setWeight(QFont.Bold)
    _title_font.setPointSize(12)

    def __init__(self, devpanel, desc_link, maxlen=20):
        super().__init__()
        self._devpanel = devpanel
        self._desc_link = desc_link
        self._name = desc_link.name
        self._fullname = '.'.join((devpanel._fullname, self._name))
        self._id = desc_link.id
        self._maxlen = maxlen
        self._commands = []
        self._updates = []
        self._logger = devpanel._logger

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self._outer_layout = QHBoxLayout()
        self.setLayout(self._outer_layout)
        self._layout = QVBoxLayout()
        self._outer_layout.addLayout(self._layout)
        self._row_list = [QHBoxLayout()]
        self._layout.addLayout(self._row_list[-1])
        self._generate_UI()

    def _generate_UI(self):
        """Populate the panel by the description _devpanelice link _desc_link.

        Returns: None
        """
        if self._desc_link.name != "":
            self._label = QLabel(self._name)
            self._label.setFont(self._title_font)
            self.__outer_layout.insertWidget(0, self._label)

        col_index = 0
        for link in self._desc_link.links:
            try:
                if link.type == link_pb2.Link.COMMAND:
                    widget = CommandWidget(self, link)
                    self._commands.append(widget)
                else:  # link.type == link_pb2.Link.UPDATE:
                    widget = UpdateWidget(self, link)
                    self._updates.append(widget)

                if col_index + widget.widget_length > self._maxlen:
                    self._row_list[-1].addStretch(1)
                    self._row_list.append(QHBoxLayout())
                    self._layout.addLayout(self.row_list[-1])
                    col_index = 0
                self._row_list[-1].addWidget(widget)
                col_index += widget.widget_length
            except Exception:
                # Already logged
                pass
        self._row_list[-1].addStretch(1)

    def update_from(self, grp_link):
        """Update contents accroding to grp_link

        Returns: None
        """
        for link in grp_link.links:
            try:
                widget = self._updates[link.id]
                widget.update_from(link)
            except IndexError:
                self._logger.error(self._fullname, "Wrong update id: {id}".format(id=link.id))

    def get_link(self, dev_link):
        """Get commands from the list of Commands, wrap them in a GroupLink, then
        append them to dev_link.

        Returns: the created link_pb2.GroupLink or None if GroupLink is empty
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self._id
        for cmd in self._commands:
            cmd.get_link(grp_link)
        if not grp_link.links:  # empty
            del dev_link.grp_links[-1]
            return None
        else:
            return grp_link

    def get_full_link(self, dev_link):
        """Get commands from the list of Commands, wrap them in a GroupLink, then
        append them to dev_link. This GroupLink also contains additional
        information such as the group's name. This is used for restoring
        commands.

        Returns: the created link_pb2.GroupLink or None if GroupLink is empty
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self._id
        grp_link.name = self._name
        for cmd in self._commands:
            cmd.get_full_link(grp_link)
        if not grp_link.links:  # empty
            del dev_link.grp_links[-1]
            return None
        else:
            return grp_link

    def get_status(self, dev_link):
        """Collect status args from widgets and wrap them into a GroupLink,
        then append it to DeviceLink dev_link.

        Returns: the created link_pb2.GroupLink or None is empty
        """
        if self._updates:
            grp_link = dev_link.grp_links.add()
            grp_link.id = self._id
            grp_link.name = self._name
            for update in self._updates:
                update.get_status(grp_link)
            return grp_link
        else:
            return None


class DevicePanel(QFrame):
    """A subpanel to display device status and _commands. It is
    generated automatically according to the description link _desc_link.
    """
    _title_font = QFont()
    _title_font.setWeight(QFont.Bold)
    _title_font.setPointSize(16)
    _datefmt = '%Y-%m-%d %H:%M:%S'

    def __init__(self, nodepanel, desc_link):
        super().__init__()
        self._nodepanel = nodepanel
        self._desc_link = desc_link
        self._name = desc_link.name
        self._fullname = '.'.join((nodepanel._fullname, self._name))
        self._id = desc_link.id
        self._groups = []
        self._logger = nodepanel._logger
        self._name_dict = None  # lazy initialization

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLineWidth(1.5)
        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._headline = QHBoxLayout()
        self._layout.addLayout(self._headline)
        self._headline.addStretch(1)
        self._save_status_btn = QPushButton("Save status")
        self._save_status_btn.clicked.connect(self._save_status)
        self._save_cmd_btn = QPushButton("Save commands")
        self._save_cmd_btn.clicked.connect(self._save_cmd)
        self._load_cmd_btn = QPushButton("Load commands")
        self._load_cmd_btn.clicked.connect(self._load_cmd)
        self._apply_all_btn = QPushButton("Apply all")
        self._apply_all_btn.clicked.connect(self._apply_all)
        self._headline.addWidget(self._save_status_btn)
        self._headline.addWidget(self._save_cmd_btn)
        self._headline.addWidget(self._load_cmd_btn)
        self._headline.addWidget(self._apply_all_btn)

        self._generate_UI()

    def _generate_UI(self):
        """Populate the panel by _desc_link.

        Returns: None
        """
        self._title = QLabel(self._desc_link.name)
        self._title.setFont(self._title_font)
        self._headline.insertWidget(0, self._title)
        # TODO: apply all , save, load button
        for grp_link in self._desc_link.grp_links:
            grp = GroupPanel(self, grp_link)
            self._groups.append(grp)
            self._layout.addWidget(grp)

    @pyqtSlot()
    def _save_status(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        time = datetime.today().strftime(self._datefmt)
        stfile = os.path.join(
            pdir, "save", "{name} {time} status{ext}".format(name=self._fullname,
                time=time, ext='.txt'))
        filename = QFileDialog.getSaveFileName(self, 'Save status file',
            stfile, 'Data file (*.txt);;Any file (*)', None, QFileDialog.DontUseNativeDialog)
        if filename[0]:
            try:
                status_link = self.get_status()
                if status_link is not None:
                    with open(filename, mode='w', encoding='utf-8') as f:
                        f.write(str(status_link))
            except OSError:
                self._logger.exception(self._fullname, "Failed to create file: {filename}".format(filename=filename))

    @pyqtSlot()
    def _save_cmd(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        time = datetime.today().strftime(self._datefmt)
        stfile = os.path.join(
            pdir, "save", "{name} {time} commands{ext}".format(name=self._fullname,
                time=time, ext='.txt'))
        filename = QFileDialog.getSaveFileName(self, 'Save command file',
            stfile, 'Data file (*.txt);;Any file (*)', None, QFileDialog.DontUseNativeDialog)
        if filename[0]:
            cmd_link = self.get_full_link()
            if cmd_link is not None:
                bin_link = cmd_link.SerializeToString()
                try:
                    with open(filename, mode='w', encoding='utf-8') as f:
                        f.write(base64.b64encode(bin_link).decode('ascii'))
                        f.write('\n\n')
                        f.write(str(cmd_link))
                except OSError:
                    self._logger.exception(self._fullname, "Failed to create file: {filename}".format(filename=filename))

    @pyqtSlot()
    def _load_cmd(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        savedir = os.path.join(pdir, "save")
        filename = QFileDialog.getOpenFileName(self, 'Open command file',
            savedir, 'Data file (*.txt);;Any file (*)', None, QFileDialog.DontUseNativeDialog)
        if filename[0]:
            try:
                with open(filename, mode='r',encoding='utf-8') as f:
                    b64_bin = f.readline()[:-1]
            except OSError:
                self._logger.exception(self._fullname, "Failed to open file: {filename}".format(filename=filename))
                return
            try:
                bin_link = base64.decodebytes(b64_bin.encode('ascii'))
                cmd_link = link_pb2.NodeLink.FromString(bin_link)
            except DecodeError:
                self._logger.error(self._fullname, "Failed to parse commands from file: {filename}".format(filename=filename))
                return
            self.set_from_link(cmd_link)

    def update_from(self, dev_link):
        """Update contents accroding to dev_link.

        Returns: None
        """
        for grp_link in dev_link.grp_links:
            try:
                grp = self._groups[grp_link.id]
                grp.update_from(grp_link)
            except IndexError:
                self._logger.error(self._fullname, "Wrong group id: {id}".format(id=grp_link.id))

    def get_link(self):
        """Get commands from the list of groups and wrap them in a DeviceLink.

        Returns: the created link_pb2.DeviceLink or None if empty.
        """
        dev_link = link_pb2.DeviceLink()
        dev_link.id = self._id
        for grp in self._groups:
            grp.get_link(dev_link)
        if not dev_link.grp_links:  # empty
            return None
        return dev_link

    def get_full_link(self):
        """Get commands from the list of groups and wrap them in a DeviceLink.
        This DeviceLink also contains additional information such as the
        device's name. This is used for restoring commands.

        Returns: the created link_pb2.DeviceLink or None if empty.
        """
        dev_link = link_pb2.DeviceLink()
        dev_link.id = self._id
        dev_link.name = self._name
        for grp in self._groups:
            grp.get_full_link(dev_link)
        if not dev_link.grp_links:  # empty
            return None
        return dev_link

    def set_from_link(self, dev_link):
        """Restore commands from dev_link.

        Returns: None
        """
        for grp_link in dev_link.grp_links:
            try:
                grp = self._groups[grp_link.id]
                if grp_link.name == grp._name:
                    #id and name both match, handle it to the group
                    grp.set_from_link(grp_link)
                    continue
            except IndexError:
                pass
            #id out of bound or name doesn't match, try to find by name
            if self._name_dict is None:
                #Initialize it now
                self._name_dict = {}
                for grp in self._groups:
                    self._name_dict[grp._name] = grp
            try:
                grp = self._name_dict[grp_link.name]
                grp.set_from_link(grp_link)
            except KeyError:
                #Nothing found, maybe log a warning in future
                pass

    def get_status(self):
        """Collect status args from groups and wrap them into a DeviceLink.

        Returns: the created link_pb2.DeviceLink or None if empty.
        """
        dev_link = link_pb2.DeviceLink()
        dev_link.id = self._id
        dev_link.name = self._name
        for grp in self._groups:
            grp.get_status(dev_link)
        if not dev_link.grp_links:  # empty
            return None
        return dev_link

    def _apply_all(self):
        """Send all _commands to _nodepanel.

        Returns: None
        """
        pass


class NodePanel(QFrame):
    """A panel to display node status and send controls to node. It is
    generated automatically according to the first description link received
    from socket.
    """
    _StyleDisabled = "QPushButton { background-color : #808080}"
    _StyleWorking = "QPushButton { background-color : #00FFFF}"
    _StyleReady = "QPushButton { background-color : #00FF00}"
    _StyleError = "QPushButton { background-color : #FF0000}"
    _title_font = QFont()
    _title_font.setWeight(QFont.Black)
    _title_font.setPointSize(18)

    def __init__(self):
        super().__init__()
        self._connected = False
        self._host_ip = None
        self._readwriter = None
        self._desc_link = None
        self._devices = []
        self._logger = Logger()
        self._fullname = None
        self._initUI()

    def _initUI(self):
        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLineWidth(2)

        self._outer_layout = QGridLayout()
        self.setLayout(self._outer_layout)
        self._outer_layout.setColumnStretch(0, 0)
        self._outer_layout.setColumnStretch(1, 0)
        self._outer_layout.setColumnStretch(2, 1)
        self._outer_layout.setColumnStretch(3, 0)
        self._host_edit = QLineEdit("127.0.0.1")
        self._host_edit.setMinimumWidth(100)
        self._outer_layout.addWidget(self._host_edit, 0, 0)
        self._status_light = QPushButton()
        self._status_light.setStyleSheet(self._StyleDisabled)
        self._status_light.setFixedSize(24, 24)
        self._outer_layout.addWidget(self._status_light, 0, 1)
        self._title = QLabel("Not connected")
        self._title.setFont(self._title_font)
        self._title.setAlignment(Qt.AlignCenter)
        self._outer_layout.addWidget(self.title, 0, 2)
        self._status_bar = QStatusBar()
        self._outer_layout.addWidget(self._status_bar, 5, 0, 1, 4)
        self._connect_btn = QPushButton("Connect")
        self._reconnect_btn = QPushButton("Reconnect")
        self._disconnect_btn = QPushButton("Disconnect")
        self._close_btn = QPushButton("X")
        self._close_btn.setFixedSize(24, 24)
        self._outer_layout.addWidget(self._connect_btn, 1, 0,)
        self._outer_layout.addWidget(self._reconnect_btn, 2, 0)
        self._outer_layout.addWidget(self._disconnect_btn, 3, 0)
        self._outer_layout.addWidget(self._close_btn, 0, 3, 1, 2)
        self._layout = QVBoxLayout()
        self._outer_layout.addLayout(self._layout, 1, 1, 4, 3)

        self._connect_btn.clicked.connect(self._connect_btn_exec)
        self._disconnect_btn.clicked.connect(self._disconnect_btn_exec)
        self._reconnect_btn.clicked.connect(self._reconnect_btn_exec)
        self._close_btn.clicked.connect(self._close)

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
        self._title.setText(self._desc_link.name)
        for dev_link in self._desc_link.dev_links:
            dev = DevicePanel(self, dev_link)
            self._devices.append(dev)
            self.layout.addWidget(dev)

    def send_command(self, node_link):
        if self._connected:
            bin_link = node_link.SerializeToString()
            self._readwriter.write_bin_link(bin_link)

    @pyqtSlot()
    def _connect_btn_exec(self):
        if not self._connected:
            self._clear_devices()
            self._host_ip = self._host_edit.text()
            self._status_bar.showMessage("Connecting")
            self._status_light.setStyleSheet(self._StyleWorking)
            ensure_future(self._connect())

    async def _connect(self):
        """Coroutine to make connection to node server."""
        try:
            reader, writer = await asyncio.open_connection(host=self._host_ip, port=5362)
            self._readwriter = StreamReadWriter(reader, writer)

            # Parse description link from nodeserver
            length = await varint.decode(self._readwriter)
            buf = await self._readwriter.read(length)
            while len(buf) < length:
                buf += await self.read(length-len(buf))
            node_link = link_pb2.NodeLink.FromString(buf)
            self._desc_link = node_link

            self._generate_panel()
            self._logger.set_name(#TODO)
            self._status_light.setStyleSheet(self._StyleReady)
            self._connected = True
            self._status_bar.showMessage("Ready")
            self._readwriter.write("RDY".encode("ascii"))
            ensure_future(self._handle_update_from())
        except Exception as err:
            self._connected = False
            self._status_bar.showMessage(str(err))
            self._status_light.setStyleSheet(self._StyleError)

    async def _handle_update_from(self):
        try:
            while True:
                # Parse NodeLink
                length = await varint.decode(self._readwriter)
                buf = await self._readwriter.read(length)
                while len(buf) < length:
                    buf += await self._readwriter.read(length-len(buf))
                update_link = link_pb2.NodeLink.FromString(buf)

                for dev_link in update_link.dev_links:
                    dev = self._devices[dev_link.id]
                    dev.update_from(dev_link)
                # A flashing light effect
                self._status_light.setStyleSheet(self._StyleWorking)
                QTimer.singleShot(100, self._light_flash)
        except EndOfStreamError:
            # server disconnects
            pass
        except (DecodeError, ProtocalError):
            # purposely drop connection
            self._readwriter.close()
        finally:
            self._status_bar.showMessage("Disconnected")
            self._status_light.setStyleSheet(self._StyleError)

    @pyqtSlot()
    def _disconnect_btn_exec(self):
        if self._connected:
            self._readwriter.close()
            self._connected = False
            self._status_bar.showMessage("Disconnected")
            self._status_light.setStyleSheet(self._StyleDisabled)

    @pyqtSlot()
    def _reconnect_btn_exec(self):
        if self._connected:
            self._readwriter.close()
            self._connected = False
            self._status_bar.showMessage("Disconnected")
            self._status_light.setStyleSheet(self._StyleDisabled)
            self._connect_btn_exec()

    @pyqtSlot()
    def _light_flash(self):
        if self._connected:
            self._status_light.setStyleSheet(self._StyleReady)

    @pyqtSlot()
    def _close(self):
        if self._connected:
            self._status_bar.showMessage(
                "Please disconnect before closing panel")
        else:
            self.deleteLater()
