import os
import sys
import asyncio
from asyncio import ensure_future, IncompleteReadError
import traceback
from datetime import datetime

from PyQt5.QtWidgets import (QLineEdit, QTextEdit, QPushButton, QFrame,
                             QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
                             QBoxLayout, QStatusBar, QFileDialog)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import pyqtSlot, QTimer, Qt

from google.protobuf.message import DecodeError
from google.protobuf import json_format

from .common import StreamReadWriter, write_link
from .link_pb2 import Link, DeviceLink, NodeLink
from . import varint
from .widgets import (UStrWidget, UFloatWidget, UIntWidget, UBoolWidget,
                    UEnumWidget, CStrWidget, CFloatWidget, CIntWidget,
                    CBoolWidget, CEnumWidget)


class Logger(QTextEdit):
    """A non-persistent object-level logger with a QTextEdit display"""
    datefmt = '%Y-%m-%d %H:%M:%S'
    fmt = "[{source}:{level}]\t{asctime}\t{name}:\t{message}\n{exc}"

    def __init__(self, btn=None, datefmt=None, fmt=None):
        super().__init__()
        self._btn = btn
        self._datefmt = datefmt or Logger.datefmt
        self._fmt = fmt or Logger.fmt

        self.setReadOnly(True)
        self.setWindowTitle("Log Viewer")
        self.resize(800, 400)
        self.hide()

    def info(self, name, message, source="CONTROL"):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="INFO", name=name, message=message, exc="")
        self.insertPlainText(record)

    def warning(self, name, message, source="CONTROL"):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="WARNING", name=name, message=message, exc="")
        self.insertPlainText(record)
        self._notify_btn()

    def error(self, name, message, source="CONTROL"):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="ERROR", name=name, message=message, exc="")
        self.insertPlainText(record)
        self._notify_btn()

    def exception(self, name, message, source="CONTROL"):
        """Show the message and traceback."""
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="EXCEPTION", name=name, message=message, exc=traceback.format_exc())
        self.insertPlainText(record)
        self._notify_btn()

    def remote(self, record):
        """Show log record received from nodeserver"""
        self.insertPlainText(record)
        self._notify_btn()

    def _notify_btn(self):
        if self._btn:
            if not self.isVisible():
                self._btn.setText("(New) Log")


class CommandWidget(QFrame):
    """A widget to handle user commands."""
    _widget_dict = {
        "str": CStrWidget,
        "float": CFloatWidget,
        "int": CIntWidget,
        "bool": CBoolWidget,
        "enum": CEnumWidget,
    }
    StyleNormal = "CommandWidget { border: 1px solid #E6E6E6; }"
    StyleError = "CommandWidget { border: 1px solid #FF0000; }"

    def __init__(self, dev_panel, desc_link):
        super().__init__()
        self._dev_panel = dev_panel
        self._desc_link = desc_link
        self.id_ = desc_link.id
        self.name = desc_link.name
        self.grp = desc_link.group
        if self.grp:
            self._fullname = '.'.join((dev_panel._fullname, self.grp, self.name))
        else:
            self._fullname = '.'.join((dev_panel._fullname, self.name))
        self._widget_list = []
        self._full_widget_list = []
        self._logger = dev_panel._logger

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self.StyleNormal)
        self._layout = QHBoxLayout()
        self.setLayout(self._layout)
        self._generate_UI()

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    @property
    def widget_length(self):
        return len(self._full_widget_list)

    def _generate_UI(self):
        """Parse desc link.sigs and generate corresponding widgets. link.sigs
        is a list describing the signature of command.
        These command widgets should implement `get_arg() -> str` to
        get arguments. An empty string means invalid input.
        n-th link.args is passed to n-th widget's __init__ as extra arg.

        Returns: None
        """
        if self._desc_link.sigs:
            label = QLabel(self._desc_link.name)
            self._full_widget_list.append(label)
            for i, sig in enumerate(self._desc_link.sigs):
                if len(self._desc_link.args) > i:
                    ext_arg = self._desc_link.args[i]
                else:
                    ext_arg = None
                widget = self._widget_dict[sig](ext_arg)
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

    @pyqtSlot()
    def _light_flash(self):
        """A flashing light effect"""
        self.setStyleSheet(self.StyleNormal)

    def get_cmd(self, dev_link):
        """Collect args from widgets and wrap them into a link, then append it
        to dev_link.

        Returns: the created Link or None if invalid
        """
        cmds = tuple(widget.get_arg() for widget in self._widget_list)
        if not (cmds and all(cmds)):
            return None
        else:
            link = dev_link.links.add()
            link.id = self.id_
            link.args.extend(cmds)
            return link

    def get_full_cmd(self, dev_link):
        """Collect args from widgets and wrap them into a link, then append it
        to dev_link. This link also contains additional information such as the
        command's name. This is used for restoring commands.

        Returns: the created Link or None if invalid
        """
        cmds = tuple(widget.get_arg() for widget in self._widget_list)
        if not (cmds and all(cmds)):
            return None
        else:
            link = dev_link.links.add()
            link.type = Link.COMMAND
            link.id = self.id_
            link.name = self.name
            link.group = self.grp
            link.sigs.extend(self._desc_link.sigs)
            link.args.extend(cmds)
            return link

    def set_cmd_from(self, link):
        """Restore commands from link.

        Returns: None
        """
        if link.sigs == self._desc_link.sigs:
            # Same signature is garanteed so unnecessary to check for index
            # here
            for i, arg in enumerate(link.args):
                try:
                    self._widget_list[i].set_arg(arg)
                except Exception:
                    pass    # Too small an error to be logged

    @pyqtSlot()
    def _send_command(self):
        """Send command to nodeserver."""
        cmds = tuple(widget.get_arg() for widget in self._widget_list)
        if not all(cmds):
            self.setStyleSheet(self.StyleError)
            QTimer.singleShot(1000, self._light_flash)
            return
        else:
            node_link = NodeLink()
            dev_link = node_link.dev_links.add()
            dev_link.id = self._dev_panel.id_
            link = dev_link.links.add()
            link.id = self.id_
            link.args.extend(cmds)
            self._dev_panel.send_command(node_link)


class UpdateWidget(QFrame):
    """A widget to handle updates from node."""
    _widget_dict = {
        "str": UStrWidget,
        "float": UFloatWidget,
        "int": UIntWidget,
        "bool": UBoolWidget,
        "enum": UEnumWidget,
    }
    StyleNormal = "UpdateWidget { border: 1px solid #E6E6E6; }"
    StyleError = "UpdateWidget { border: 1px solid #FF0000; }"

    def __init__(self, dev_panel, desc_link):
        super().__init__()
        self._dev_panel = dev_panel
        self._desc_link = desc_link
        self.id_ = desc_link.id
        self.name = desc_link.name
        self.grp = desc_link.group
        if self.grp:
            self._fullname = '.'.join((dev_panel._fullname, self.grp, self.name))
        else:
            self._fullname = '.'.join((dev_panel._fullname, self.name))
        self._widget_list = []
        self._full_widget_list = []
        self._logger = dev_panel._logger

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(self.StyleNormal)
        self._layout = QHBoxLayout()
        self.setLayout(self._layout)
        self._generate_UI()

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    @property
    def widget_length(self):
        return len(self._full_widget_list)

    def _generate_UI(self):
        """Parse desc link.sigs and generate corresponding widgets. link.sigs
        is a list describing the signature of update.
        Currently the following types are implemented for updates:
        These update widgets should implement `update_from(str)` to update
        its contents. n-th link.args is passed to n-th widget's __init__
        as extra arg.

        Returns: None
        """
        if self._desc_link.sigs:
            label = QLabel(self.name)
            self._full_widget_list.append(label)
            for i, sig in enumerate(self._desc_link.sigs):
                if len(self._desc_link.args) > i:
                    ext_arg = self._desc_link.args[i]
                else:
                    ext_arg = None
                widget = self._widget_dict[sig](ext_arg)
                self._widget_list.append(widget)
                self._full_widget_list.append(widget)

        for widget in self._full_widget_list:
            self._layout.addWidget(widget)

    @pyqtSlot()
    def _light_flash(self):
        """A flashing light effect"""
        self.setStyleSheet(self.StyleNormal)

    def update_from(self, link):
        """Update contents from link.

        Returns: None
        """
        try:
            for i, arg in enumerate(link.args):
                self._widget_list[i].set_arg(arg)
        except Exception:
            self._log_exception("Failed to display update.")
            self.setStyleSheet(self.StyleError)
            QTimer.singleShot(1000, self._light_flash)

    def get_status(self, dev_link):
        """Collect status args from widgets and wrap them into a link,
        then append it to dev_link.

        Returns: the created Link
        """
        link = dev_link.links.add()
        link.type = Link.UPDATE
        link.id = self.id_
        link.name = self.name
        link.group = self.grp
        link.sigs.extend(self._desc_link.sigs)
        link.args.extend(widget.get_arg() for widget in self._widget_list)
        return link


class GroupPanel(QFrame):
    """A subpanel to display a group of operations. maxlen is the
    maximum number of basic QWidgets of the same type (command/update)
    on a single line.
    """
    title_font = QFont()
    title_font.setWeight(QFont.Bold)
    title_font.setPointSize(12)

    def __init__(self, name="", maxlen=15):
        super().__init__()
        self._maxlen = maxlen

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLayout(QHBoxLayout(self))
        if name != "":
            label = QLabel(name, self)
            label.setFont(self.title_font)
            self.layout().addWidget(label)

        self._update_layout = QVBoxLayout()
        self.layout().addLayout(self._update_layout)
        self._update_row = QHBoxLayout()
        self._update_layout.addLayout(self._update_row)

        self._cmd_layout = QVBoxLayout()
        self.layout().addLayout(self._cmd_layout)
        self._cmd_row = QHBoxLayout()
        self._cmd_row.setDirection(QBoxLayout.RightToLeft)
        self._cmd_layout.addLayout(self._cmd_row)

        self._num_widgets = 0
        self._update_col_index = 0
        self._cmd_col_index = 0

    def add_widget(self, widget):
        """Add widget to this group.

        Returns: None
        """
        if isinstance(widget, CommandWidget):
            self.add_cmd_widget(widget)
        elif isinstance(widget, UpdateWidget):
            self.add_update_widget(widget)

    def add_cmd_widget(self, widget):
        """Add command widget to this group.

        Returns: None
        """
        if self._cmd_col_index + widget.widget_length > self._maxlen:
            self._cmd_row.addStretch(1)
            self._cmd_row = QHBoxLayout()
            self._cmd_row.setDirection(QBoxLayout.RightToLeft)
            self._cmd_layout.addLayout(self._cmd_row)
            self._cmd_col_index = 0
        self._cmd_row.insertWidget(0, widget)
        self._cmd_col_index += widget.widget_length
        self._num_widgets += 1

    def add_update_widget(self, widget):
        """Add command widget to this group.

        Returns: None
        """
        if self._update_col_index + widget.widget_length > self._maxlen:
            self._update_row.addStretch(1)
            self._update_row = QHBoxLayout()
            self._update_layout.addLayout(self._update_row)
            self._update_col_index = 0
        self._update_row.addWidget(widget)
        self._update_col_index += widget.widget_length
        self._num_widgets += 1

    def finish_adding(self):
        """Call this method when all widgets have been added to this group panel.
        It re-arranges widgets and release intermediate variables.

        Returns: True is this panel has widgets or False if it is empty.
        """
        if self._num_widgets == 0:
            return False
        else:
            self._cmd_row.addStretch(1)
            self._update_row.addStretch(1)
            del self._num_widgets
            del self._cmd_col_index
            del self._update_col_index
            return True


class DevicePanel(QFrame):
    """A subpanel to display device status and _commands. It is
    generated automatically according to the description link _desc_link.
    """
    title_font = QFont()
    title_font.setWeight(QFont.Bold)
    title_font.setPointSize(16)
    if os.name == 'nt':
        datefmt = '%Y-%m-%d %H-%M-%S'
    else:
        datefmt = '%Y-%m-%d %H:%M:%S'

    def __init__(self, node_panel, desc_link):
        super().__init__()
        self._node_panel = node_panel
        self._desc_link = desc_link
        self.id_ = desc_link.id
        self.name = desc_link.name
        self._fullname = '.'.join((node_panel._fullname, self.name))
        self._logger = node_panel._logger
        self._commands = {}
        self._updates = {}
        self._groups = {}
        self._name_dict = None  # lazy initialization

        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLineWidth(1.5)
        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._layout.setSpacing(0)
        self._headline = QHBoxLayout()
        self._layout.addLayout(self._headline)
        self._headline.setSpacing(10)
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

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    def _generate_UI(self):
        """Populate the panel by desc_link.

        Returns: None
        """
        self._title = QLabel(self.name)
        self._title.setFont(self.title_font)
        self._headline.insertWidget(0, self._title)

        for grp in self._desc_link.groups:
            if grp.startswith('_'):
                # Invisible groups
                continue
            grp_panel = GroupPanel(grp)
            self._groups[grp] = grp_panel
            self._layout.addWidget(grp_panel)

        for link in self._desc_link.links:
            if link.group.startswith('_'):
                # in invisible group
                continue
            if link.type == Link.COMMAND:
                try:
                    widget = CommandWidget(self, link)
                except Exception:
                    if link.group:
                        fullname = '.'.join((link.group, link.name))
                    else:
                        fullname = link.name
                    self._log_exception(
                        "Failed to create widget: {name}".format(name=fullname))
                    continue
                self._commands[link.id] = widget
                try:
                    self._groups[link.group].add_cmd_widget(widget)
                except KeyError:
                    self._log_error("Unknown group name: {name}".format(name=link.group))
            else:  # link.type == Link.UPDATE:
                try:
                    widget = UpdateWidget(self, link)
                except Exception:
                    if link.group:
                        fullname = '.'.join((link.group, link.name))
                    else:
                        fullname = link.name
                    self._log_exception(
                        "Failed to create widget: {name}".format(name=fullname))
                    continue
                self._updates[link.id] = widget
                try:
                    self._groups[link.group].add_update_widget(widget)
                except KeyError:
                    self._log_error("Unknown group name: {name}".format(name=link.group))

        empty_groups = []
        for grp, grp_panel in self._groups.items():
            if not grp_panel.finish_adding():
                # empty group, delete this panel
                empty_groups.append(grp)
                grp_panel.deleteLater()
        for grp in empty_groups:
            del self._groups[grp]

    @pyqtSlot()
    def _save_status(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        time = datetime.today().strftime(self.datefmt)
        stfile = os.path.join(
            pdir, "save", "{name} {time} status{ext}".format(name=self._fullname,
                                                             time=time, ext='.json'))
        filenames = QFileDialog.getSaveFileName(self, 'Save status file',
                                                stfile, 'Json file (*.json);;Any file (*)',
                                                None, QFileDialog.DontUseNativeDialog)
        filename = filenames[0]
        if filename:
            status_link = self._get_status_link()
            if status_link is not None:
                json_link = json_format.MessageToJson(status_link)
                try:
                    with open(filename, mode='w', encoding='ascii') as f:
                        f.write(json_link)
                except OSError:
                    self._log_exception("Failed to create file: {filename}".format(filename=filename))

    def get_status(self, node_link):
        """Collect status args from updates and wrap them into a DeviceLink,
        then append it to node_link.

        Returns: the created DeviceLink or None if empty.
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id_
        dev_link.name = self.name
        for update in self._updates.values():
            update.get_status(dev_link)
        if not dev_link.links:  # empty
            del node_link.dev_links[-1]
            return None
        else:
            return dev_link

    def _get_status_link(self):
        """Collect status args from updates and wrap them into a DeviceLink.

        Returns: the created DeviceLink or None if empty.
        """
        dev_link = DeviceLink()
        dev_link.id = self.id_
        dev_link.name = self.name
        for update in self._updates.values():
            update.get_status(dev_link)
        if not dev_link.links:  # empty
            return None
        else:
            return dev_link

    @pyqtSlot()
    def _save_cmd(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        time = datetime.today().strftime(self.datefmt)
        stfile = os.path.join(
            pdir, "save", "{name} {time} commands{ext}".format(name=self._fullname,
                                                               time=time, ext='.json'))
        filenames = QFileDialog.getSaveFileName(self, 'Save command file',
                                                stfile, 'Json file (*.json);;Any file (*)',
                                                None, QFileDialog.DontUseNativeDialog)
        filename = filenames[0]
        if filename:
            cmd_link = self._get_full_cmd_link()
            if cmd_link is not None:
                json_link = json_format.MessageToJson(cmd_link)
                try:
                    with open(filename, mode='w', encoding='ascii') as f:
                        f.write(json_link)
                except OSError:
                    self._log_exception("Failed to create file: {filename}".format(filename=filename))

    def _get_full_cmd_link(self):
        """Get commands from the commands and wrap them in a DeviceLink.
        This DeviceLink also contains additional information such as the
        device's name. This is used for restoring commands.

        Returns: the created DeviceLink or None if empty.
        """
        dev_link = DeviceLink()
        dev_link.id = self.id_
        dev_link.name = self.name
        for cmd in self._commands.values():
            cmd.get_full_cmd(dev_link)
        if not dev_link.links:  # empty
            return None
        else:
            return dev_link

    @pyqtSlot()
    def _load_cmd(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        savedir = os.path.join(pdir, "save")
        filenames = QFileDialog.getOpenFileName(self, 'Open command file',
                                                savedir, 'Json file (*.json);;Any file (*)', None, QFileDialog.DontUseNativeDialog)
        filename = filenames[0]
        if filename:
            try:
                with open(filename, mode='r', encoding='ascii') as f:
                    json_link = f.read()
            except OSError:
                self._log_exception("Failed to open file: {filename}".format(filename=filename))
                return
            try:
                cmd_link = DeviceLink()
                json_format.Parse(json_link, cmd_link, True)
            except json_format.ParseError:
                self._log_error("Failed to decode commands from file: {filename}".format(filename=filename))
                return
            self.set_cmd_from(cmd_link)

    def set_cmd_from(self, dev_link):
        """Restore commands from dev_link.

        Returns: None
        """
        for link in dev_link.links:
            try:
                cmd = self._commands[link.id]
                if link.name == cmd.name and link.group == cmd.grp:
                    # id, name and group all match
                    cmd.set_cmd_from(link)
                    continue
            except KeyError:
                pass
            # id, name or group doesn't match, try to find by group.name
            if self._name_dict is None:
                # Initialize it now
                self._name_dict = {}
                for cmd in self._commands.values():
                    self._name_dict["{grp}.{name}".format(
                        grp=cmd.grp, name=cmd.name)] = cmd
            try:
                cmd = self._name_dict["{grp}.{name}".format(
                    grp=link.group, name=link.name)]
                cmd.set_cmd_from(link)
            except KeyError:
                # Nothing found, maybe log a warning in future
                pass

    @pyqtSlot()
    def _apply_all(self):
        """Send all valid commands to nodeserver.
        """
        node_link = NodeLink()
        if self.get_cmd(node_link):
            self.send_command(node_link)

    def update_from(self, dev_link):
        """Update contents accroding to dev_link

        Returns: None
        """
        for link in dev_link.links:
            try:
                update = self._updates[link.id]
                update.update_from(link)
            except KeyError:
                self._log_error("Wrong update id: {id}".format(id=link.id))

    def get_cmd(self, node_link):
        """Get commands from the list of Commands and wrap them in a DeviceLink,
        then append it to node_link.

        Returns: the created DeviceLink or None if empty.
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id_
        for cmd in self._commands.values():
            cmd.get_cmd(dev_link)
        if not dev_link.links:  # empty
            del node_link.dev_links[-1]
            return None
        else:
            return dev_link

    def get_full_cmd(self, node_link):
        """Get commands from the list of Commands and wrap them in a DeviceLink,
        then append it to node_link. This DeviceLink also contains additional
        information such as the device's name. This is used for restoring commands.

        Returns: the created DeviceLink or None if empty.
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id_
        dev_link.name = self.name
        for cmd in self._commands.values():
            cmd.get_full_cmd(dev_link)
        if not dev_link.links:  # empty
            del node_link.dev_links[-1]
            return None
        else:
            return dev_link

    def send_command(self, node_link):
        """Send command node_link to nodeserver."""
        self._node_panel.send_command(node_link)


class NodePanel(QFrame):
    """A panel to display node status and send controls to node. It is
    generated automatically according to the first description link received.
    """
    StyleDisabled = "QPushButton { background-color : #808080}"
    StyleWorking = "QPushButton { background-color : #00FFFF}"
    StyleReady = "QPushButton { background-color : #00FF00}"
    StyleError = "QPushButton { background-color : #FF0000}"
    title_font = QFont()
    title_font.setWeight(QFont.Black)
    title_font.setPointSize(18)
    if os.name == 'nt':
        datefmt = '%Y-%m-%d %H-%M-%S'
    else:
        datefmt = '%Y-%m-%d %H:%M:%S'

    def __init__(self, parent=None, loop=None):
        super().__init__(parent)
        self._loop = loop or asyncio.get_event_loop()
        self._connected = False
        self._host_ip = None
        self._readwriter = None
        self._desc_link = None
        self._devices = {}
        self._fullname = ""
        self._peaceful_disconnect = False

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
        self._status_light.setStyleSheet(self.StyleDisabled)
        self._status_light.setFixedSize(24, 24)
        self._outer_layout.addWidget(self._status_light, 0, 1)
        self._title = QLabel("Not connected")
        self._title.setFont(self.title_font)
        self._title.setAlignment(Qt.AlignCenter)
        self._outer_layout.addWidget(self._title, 0, 2)
        self._status_bar = QStatusBar()
        self._outer_layout.addWidget(self._status_bar, 9, 0, 1, 4)

        self._connect_btn = QPushButton("Connect")
        self._disconnect_btn = QPushButton("Disconnect")
        self._save_status_btn = QPushButton("Save status")
        self._save_cmd_btn = QPushButton("Save commands")
        self._load_cmd_btn = QPushButton("Load commands")
        self._apply_all_btn = QPushButton("Apply all")
        self._log_btn = QPushButton("Log")
        self._logger = Logger(self._log_btn)
        self._close_btn = QPushButton("X")
        self._close_btn.setFixedSize(24, 24)
        self._outer_layout.addWidget(self._connect_btn, 1, 0)
        self._outer_layout.addWidget(self._disconnect_btn, 2, 0)
        self._outer_layout.addWidget(self._save_status_btn, 4, 0)
        self._outer_layout.addWidget(self._save_cmd_btn, 5, 0)
        self._outer_layout.addWidget(self._load_cmd_btn, 6, 0)
        self._outer_layout.addWidget(self._apply_all_btn, 7, 0)
        self._outer_layout.addWidget(self._log_btn, 8, 0)
        self._outer_layout.addWidget(self._close_btn, 0, 3, 1, 2)
        self._layout = QVBoxLayout()
        self._outer_layout.addLayout(self._layout, 1, 1, 8, 3)
        self._layout.setSpacing(15)

        self._connect_btn.clicked.connect(self._connect_btn_exec)
        self._disconnect_btn.clicked.connect(self._disconnect_btn_exec)
        self._save_status_btn.clicked.connect(self._save_status)
        self._save_cmd_btn.clicked.connect(self._save_cmd)
        self._load_cmd_btn.clicked.connect(self._load_cmd)
        self._apply_all_btn.clicked.connect(self._apply_all)
        self._log_btn.clicked.connect(self._log_btn_exec)
        self._close_btn.clicked.connect(self._close)

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    def _log_remote(self, msg, **kargs):
        self._logger.remote(msg, **kargs)

    def _clear_devices(self):
        """Remove all device panels from node panel.

        Returns: None
        """
        self._devices.clear()
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _generate_panel(self):
        """Populate the panel by the description node link.

        Returns: None
        """
        self.set_title(self._fullname)
        for dev_link in self._desc_link.dev_links:
            dev_panel = DevicePanel(self, dev_link)
            self._devices[dev_link.id] = dev_panel
            self._layout.addWidget(dev_panel)

    @pyqtSlot()
    def _connect_btn_exec(self):
        if not self._connected:
            self._clear_devices()
            self._host_ip = self._host_edit.text()
            msg = "Connecting to {ip}".format(ip=self._host_ip)
            self._status_bar.showMessage(msg)
            self._log_info(msg, source="PANEL")
            self._status_light.setStyleSheet(self.StyleWorking)
            ensure_future(self._hanlde_connection())

    async def _hanlde_connection(self):
        """Coroutine to make connection to node server."""
        try:
            reader, writer = await asyncio.open_connection(host=self._host_ip, port=5362)
            self._readwriter = StreamReadWriter(reader, writer)

            # Parse description link from nodeserver
            length = await varint.decode(self._readwriter)
            buf = await self._readwriter.readexactly(length)
            self._desc_link = NodeLink.FromString(buf)

            # Set states
            self._connected = True
            self._peaceful_disconnect = False
            self._fullname = self._desc_link.name
            self._generate_panel()
            self._status_light.setStyleSheet(self.StyleReady)
            msg = "Connected to {ip}".format(ip=self._host_ip)
            self._status_bar.showMessage(msg)
            self._log_info(msg, source="PANEL")
            self._readwriter.write("RDY".encode())

            # The work loop
            while True:
                length = await varint.decode(self._readwriter)
                buf = await self._readwriter.readexactly(length)
                update_link = NodeLink.FromString(buf)
                for record in update_link.logs:
                    self._log_remote(record)

                for dev_link in update_link.dev_links:
                    dev = self._devices[dev_link.id]
                    dev.update_from(dev_link)
                # A flashing light effect
                self._status_light.setStyleSheet(self.StyleWorking)
                QTimer.singleShot(100, self._light_flash)

        except (IncompleteReadError, ConnectionError):
            if self._peaceful_disconnect:
                msg = "Disconnected from server {ip}".format(ip=self._host_ip)
                self._status_bar.showMessage(msg)
                self._log_info(msg, source="PANEL")
                self._status_light.setStyleSheet(self.StyleDisabled)
            else:
                msg = "Server at {ip} dropped connection.".format(
                    ip=self._host_ip)
                self._status_bar.showMessage(msg)
                self._log_error(msg, source="PANEL")
                self._status_light.setStyleSheet(self.StyleError)
        except DecodeError:
            msg = "Failed to decode NodeLink."
            self._status_bar.showMessage(msg)
            self._log_error(msg, source="PANEL")
            self._status_light.setStyleSheet(self.StyleError)
        except Exception:
            msg = "Unexpected Error."
            self._status_bar.showMessage(msg)
            self._log_exception(msg, source="PANEL")
            self._status_light.setStyleSheet(self.StyleError)
        finally:
            # Make sure the connection is closed
            if self._readwriter is not None:
                self._readwriter.close()
            self._readwriter = None
            self._connected = False
            self._fullname = ""

    @pyqtSlot()
    def _disconnect_btn_exec(self):
        if self._connected:
            if self._readwriter is not None:
                self._readwriter.close()
            self._peaceful_disconnect = True
            msg = "Disconnecting from server {ip}".format(ip=self._host_ip)
            self._status_bar.showMessage(msg)

    @pyqtSlot()
    def _log_btn_exec(self):
        if self._logger.isVisible():
            self._logger.hide()
        else:
            self._log_btn.setText("Log")
            self._logger.show()

    @pyqtSlot()
    def _light_flash(self):
        if self._connected:
            self._status_light.setStyleSheet(self.StyleReady)

    @pyqtSlot()
    def _close(self):
        if self._connected:
            self._status_bar.showMessage(
                "Please disconnect before closing panel.")
        else:
            self._logger.deleteLater()
            self.deleteLater()

    def get_status_link(self):
        """Collect status args from devices and wrap them into a NodeLink.

        Returns: the created NodeLink or None if empty.
        """
        node_link = NodeLink()
        for dev in self._devices.values():
            dev.get_status(node_link)
        if not node_link.dev_links:  # empty
            return None
        else:
            node_link.name = self._fullname
            return node_link

    def send_command(self, node_link):
        if self._connected:
            write_link(self._readwriter, node_link)

    @pyqtSlot()
    def _save_status(self):
        """Save all status in node to json file."""
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        time = datetime.today().strftime(self.datefmt)
        stfile = os.path.join(
            pdir, "save", "{name} {time} status{ext}".format(name=self._fullname,
                                                             time=time, ext='.json'))
        filenames = QFileDialog.getSaveFileName(self, 'Save status file',
                                                stfile, 'Json file (*.json);;Any file (*)',
                                                None, QFileDialog.DontUseNativeDialog)
        filename = filenames[0]
        if filename:
            status_link = self.get_status_link()
            if status_link is not None:
                json_link = json_format.MessageToJson(status_link)
                try:
                    with open(filename, mode='w', encoding='ascii') as f:
                        f.write(json_link)
                except OSError:
                    self._log_exception("Failed to create file: {filename}".format(filename=filename))

    @pyqtSlot()
    def _save_cmd(self):
        """Save all valid commands in node to json file."""
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        time = datetime.today().strftime(self.datefmt)
        stfile = os.path.join(
            pdir, "save", "{name} {time} commands{ext}".format(name=self._fullname,
                                                               time=time, ext='.json'))
        filenames = QFileDialog.getSaveFileName(self, 'Save command file',
                                                stfile, 'Json file (*.json);;Any file (*)',
                                                None, QFileDialog.DontUseNativeDialog)
        filename = filenames[0]
        if filename:
            cmd_link = self._get_full_cmd_link()
            if cmd_link is not None:
                json_link = json_format.MessageToJson(cmd_link)
                try:
                    with open(filename, mode='w', encoding='ascii') as f:
                        f.write(json_link)
                except OSError:
                    self._log_exception("Failed to create file: {filename}".format(filename=filename))

    def get_cmd_link(self):
        """Get commands from the list of devices and wrap them in a NodeLink.

        Returns: the created DeviceLink or None if empty.
        """
        node_link = NodeLink()
        for dev in self._devices.values():
            dev.get_cmd(node_link)
        if not node_link.dev_links:  # empty
            return None
        else:
            return node_link

    def _get_full_cmd_link(self):
        """Get commands from devices and wrap them in a NodeLink.
        This NodeLink also contains additional information for
        restoring commands.

        Returns: the created NodeLink or None if empty.
        """
        node_link = NodeLink()
        node_link.name = self._fullname
        for dev in self._devices.values():
            dev.get_full_cmd(node_link)
        if not node_link.dev_links:  # empty
            return None
        else:
            return node_link

    @pyqtSlot()
    def _load_cmd(self):
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        savedir = os.path.join(pdir, "save")
        filenames = QFileDialog.getOpenFileName(self, 'Open command file',
                                                savedir, 'Json file (*.json);;Any file (*)', None, QFileDialog.DontUseNativeDialog)
        filename = filenames[0]
        if filename:
            try:
                with open(filename, mode='r', encoding='ascii') as f:
                    json_link = f.read()
            except OSError:
                self._log_exception("Failed to open file: {filename}".format(filename=filename))
                return
            try:
                cmd_link = NodeLink()
                json_format.Parse(json_link, cmd_link, True)
            except json_format.ParseError:
                self._log_error("Failed to decode commands from file: {filename}".format(filename=filename))
                return
            self.set_cmd_from(cmd_link)

    def set_cmd_from(self, node_link):
        """Restore commands from node_link.

        Returns: None
        """
        for dev_link in node_link.dev_links:
            try:
                dev = self._devices[dev_link.id]
                if dev_link.name == dev.name:
                    # id and name both match
                    dev.set_cmd_from(dev_link)
                    continue
            except KeyError:
                pass
            for dev in self._devices.values():
                if dev_link.name == dev.name:
                    dev.set_cmd_from(dev_link)
                    break

    @pyqtSlot()
    def _apply_all(self):
        """Send all valid commands to nodeserver.
        """
        node_link = self.get_cmd_link()
        if node_link:
            self.send_command(node_link)

    def get_title(self):
        return self._title.text()

    def set_title(self, name):
        self._title.setText(name)

    def get_ip(self):
        return self._host_edit.text()

    def set_ip(self, ip):
        self._host_edit.setText(ip)
