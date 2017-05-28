"""This module defines the physical structure of a node."""
import os
import sys
import traceback
from datetime import date, datetime

from smartlink import link_pb2, isNoneStringSequence


class Logger:
    """A non-persistent object-level logger"""
    _datefmt = '%Y-%m-%d %H:%M:%S'
    _fmt = "[{level}]\t{asctime}\t{name}:\t{message}\n"

    def __init__(self, datefmt=None, fmt=None, filename=None, logbuffer=None):
        self._datefmt = datefmt or SimpleLogger.datefmt
        self._fmt = fmt or SimpleLogger.fmt
        self._filename = filename
        if filename is not None:
            try:
                self._file = open(
                    filename, mode='a', buffering=1, encoding='utf-8')
            except OSError:
                traceback.print_exc()
                self._file = None
        else:
            self._file = None
        self._buffer = logbuffer

    def close(self):
        """Close the logger and release its resources."""
        if self._file:
            self._file.close()
            self._file = None

    def info(self, name, message):
        """Print the message and log it to file"""
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, level="INFO", name=name, message=message)
        print(record)
        if self._file:
            self._file.write(record)

    def error(self, name, message):
        """Print the message, then append it to logbuffer"""
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, level="ERROR", name=name, message=message)
        print(record)
        if self._buffer:
            self._buffer.append(record)

    def exception(self, name, message):
        """Print the message and traceback, then append them to logbuffer"""
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, level="EXCEPTION", name=name, message=message)
        record += traceback.format_exc()
        print(record)
        if self._buffer:
            self._buffer.append(record)


class Command:
    """Command is the type of operation sent by control to be executed on node."""
    __slots__ = ["_grp", "_id", "_name", "_fullname",
                 "_sigs", "_func", "_ext_args", "_logger"]

    def __init__(self, grp, id_, name, sigs, func, ext_args=None):
        self._grp = grp
        self._id = id_
        self._name = name
        self._fullname = '.'.join((grp._fullname, name))
        if not sigs:
            self._sigs = None
        elif isNoneStringSequence(sigs):
            self._sigs = sigs
        else:
            self._sigs = (sigs, )
        self._func = func
        if not ext_args:
            self._ext_args = None
        elif isNoneStringSequence(ext_args):
            self._ext_args = ext_args
        else:
            self._ext_args = (ext_args, )
        self._logger = grp._logger

    def execute(self, link):
        """Call the associated func and return the result."""
        try:
            return self._func(*link.args)
            self._logger.info(self._fullname, "Executed with arguments: {args}".format(
                args=' '.join(link.args)))
        except Exception:
            self._logger.exception(self._fullname, "Failed to execute with arguments: {args}".format(
                args=' '.join(link.args)))

    def get_desc_link(self, grp_link):
        """Generate a description link to describe this Command, then append it to grp_link.

        Returns: the created link_pb2.Link
        """
        link = grp_link.links.add()
        link.type = link_pb2.Link.COMMAND
        link.id = self._id
        link.name = self._name
        if self._sigs:
            link.sigs.extend(self._sigs)
        if self._ext_args:
            link.args.extend(self._ext_args)
        return link


class Update:
    """Update is the type of operation executed on node to display the result on
    control.
    """
    __slots__ = ["_grp", "_id", "_name", "_fullname", "_sigs",
                 "_func", "_ext_args", "_old", "_logger"]

    def __init__(self, grp, id_, name, sigs, func, ext_args=None):
        self._grp = grp
        self._id = id_
        self._name = name
        self._fullname = '.'.join((grp._fullname, name))
        if not sigs:
            self._sigs = None
        elif isNoneStringSequence(sigs):
            self._sigs = sigs
        else:
            self._sigs = (sigs, )
        self._func = func
        if not ext_args:
            self._ext_args = None
        elif isNoneStringSequence(ext_args):
            self._ext_args = ext_args
        else:
            self._ext_args = (ext_args, )
        self._old = None
        self._logger = grp._logger

    def get_link(self, grp_link):
        """Execute the associated func and if the result is different from prev,
        wrap the result in a link_pb2.Link and append it to grp_link.

        Returns: the created link_pb2.Link if has new result or None
        """
        try:
            new = self._func()
            if new == self._old:
                return None
            else:
                self._old = new
                link = grp_link.links.add()
                link.id = self._id
                if isinstance(new, tuple):
                    # func() returns multiple results
                    link.args.extend(str(result) for result in new)
                else:
                    link.args.append(str(new))
                return link
        except Exception:
            self._logger.exception(self._fullname, "Failed to update.")

    def get_full_link(self, grp_link):
        """Execute the associated func, wrap the result in a link_pb2.Link and
        append it to grp_link.

        Returns: the created link_pb2.Link
        """
        try:
            new = self._func()
            link = grp_link.links.add()
            link.id = self._id
            if isinstance(new, tuple):
                # func() returns multiple results
                link.args.extend(str(result) for result in new)
            else:
                link.args.append(str(new))
            return link
        except Exception:
            self._logger.exception(self._fullname, "Failed to update.")

    def get_desc_link(self, grp_link):
        """Generate a description link to describe this Update, then append it to grp_link.

        Returns: the created link_pb2.Link or None is signature is empty or None
        """
        if self._sigs:
            link = grp_link.links.add()
            link.type = link_pb2.Link.UPDATE
            link.id = self._id
            link.name = self._name
            link.sigs.extend(self._sigs)
            if self._ext_args:
                link.args.extend(self._ext_args)
            return link
        else:
            return None


class OperationGroup:
    """An OperationGroup is a group of interrelated Commands or Updates whose
    generated UI on control should be grouped together.
    """
    __slots__ = ["_dev", "_id", "_name", "_fullname", "_desc",
                 "_commands", "_updates", "_logger"]

    def __init__(self, dev, id_, name, desc=None):
        self._dev = dev
        self._id = id_
        self._name = name
        self._fullname = '.'.join((dev._fullname, name))
        self._desc = desc
        self._commands = []
        self._updates = []
        self._logger = dev.logger

    def add_command(self, name, sigs, func, ext_args=None):
        """Create a new Command for this group.

        Returns: the created Command.
        """
        id_ = len(self._commands)
        cmd = Command(self, id_, name, sigs, func, ext_args)
        self._commands.append(cmd)
        return cmd

    def add_update(self, name, sigs, func, ext_args=None):
        """Create a new Update for this group.

        Returns: the created Update.
        """
        id_ = len(self._updates)
        update = Update(self, id_, name, sigs, func, ext_args)
        self._updates.append(update)
        return update

    def get_link(self, dev_link):
        """Get updates from the list of Updates, wrap them in a GroupLink, then
        append them to dev_link.

        Returns: the created link_pb2.GroupLink or None if GroupLink is empty
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self._id
        for update in self._updates:
            update.get_link(grp_link)
        if not grp_link.links:  # empty
            del dev_link.grp_links[-1]
            return None
        else:
            return grp_link

    def get_full_link(self, dev_link):
        """Get full updates from the list of Updates, wrap them in a GroupLink,
        then append them to dev_link.

        Returns: the created link_pb2.GroupLink
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self._id
        for update in self._updates:
            update.get_full_link(grp_link)
        return grp_link

    def get_desc_link(self, dev_link):
        """Generate a description link to describe this OperationGroup, then
        append it to dev_link.

        Returns: the created link_pb2.GroupLink
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self._id
        grp_link.name = self._name
        if self._desc:
            grp_link.msg = self._desc
        for update in self._updates:
            update.get_desc_link(grp_link)
        for cmd in self._commands:
            cmd.get_desc_link(grp_link)
        return grp_link

    def execute(self, grp_link):
        """Handle links in grp_link to corresponding Commands and executes them.

        Returns: None
        """
        for link in grp_link.links:
            try:
                cmd = self._commands[link.id]
                cmd.execute(link)
            except IndexError:
                self._logger.error(
                    self._fullname, "Wrong command id: {id}".format(id=grp_link.id))


class Device:
    """A Device is the programming correspondence to a physical device. It may
    contain one or more OperationGroups. Device is the basic unit for configuration
    saving/loading and logging.
    """

    def __init__(self, node, id_, name, desc=None):
        self._node = node
        self._id = id_
        self._name = name
        self._fullname = '.'.join((node._fullname, name))
        self._desc = desc
        self._groups = []
        self.logger = node.logger

    def add_group(self, name, desc=None):
        """Create a new OperationGroup with name and desc.

        Returns: the created OperationGroup.
        """
        id_ = len(self._groups)
        grp = OperationGroup(self, id_, name, desc)
        self._groups.append(grp)
        return grp

    def get_link(self, node_link):
        """Get updates from groups, wrap them in a DeviceLink, then
        append them to node_link.

        Returns: the created link_pb2.DeviceLink or None if DeviceLink is empty
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self._id
        for grp in self._groups:
            grp.get_link(dev_link)
        if not dev_link.grp_links:  # empty
            del node_link.dev_links[-1]
            return None
        return dev_link

    def get_full_link(self, node_link):
        """Get full updates from groups, wrap them in a DeviceLink, then
        append them to node_link.

        Returns: the created link_pb2.DeviceLink
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self._id
        for grp in self._groups:
            grp.get_full_link(dev_link)
        return dev_link

    def get_desc_link(self, node_link):
        """Generate a description link to describe this Device, then
        append it to node_link.

        Returns: the created link_pb2.DeviceLink
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self._id
        dev_link.name = self._name
        if self._desc:
            dev_link.msg = self._desc
        for grp in self._groups:
            grp.get_desc_link(dev_link)
        return dev_link

    def execute(self, dev_link):
        """Handle links in dev_link to corresponding OperationGroups and executes them.

        Returns: None
        """
        for grp_link in dev_link.grp_links:
            try:
                grp = self._groups[grp_link.id]
                grp.execute(grp_link)
            except IndexError:
                self._logger.error(
                    self._fullname, "Wrong group id: {id}".format(id=grp_link.id))


class Node:
    """A Node in smartlink corresponds to a network terminal, usually a computer,
     to control physical devices. A Node consists of one or multiple Devices.
    Node is the basic unit of network communication with control.
    """

    def __init__(self, name, desc=None):
        self._name = name
        self._fullname = self._name
        self._desc = desc
        self._devices = []
        # Logs go to three handlers:
        #   1. All logs are printed to stdout
        #   2. Info logs about executed commands are logged to file
        #   3. Error logs are sent to Control through update link
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        logfile = os.path.join(
            pdir, "log", "{name}-{date}{ext}".format(name=name, date=str(date.today()), ext='.log'))
        self._log_buffer = []
        self.logger = Logger(filename=logfile, logbuffer=self._log_buffer)

    def close(self):
        """Safely close this node object and free its resources.

        Returns: None
        """
        self.logger.close()

    def clear_log(self):
        """Clear all log entries. This method should be called by nodeserver
        when log has been successfully sent."""
        self._log_buffer.clear()

    def create_device(self, name, desc=None):
        """Create a new Device with name and desc.

        Returns: the created Device.
        """
        id_ = len(self._devices)
        dev = Device(self, id_, name, desc)
        self._devices.append(dev)
        return dev

    def get_link(self):
        """Get updates from devices and wrap them in a NodeLink.

        Returns: the created link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        for dev in self._devices:
            dev.get_link(node_link)
        node_link.logs.extend(self._log_buffer)
        return node_link

    def get_full_link(self):
        """Get full updates from devices and wrap them in a NodeLink.

        Returns: the created link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        for dev in self._devices:
            dev.get_full_link(node_link)
        return node_link

    def get_desc_link(self):
        """Generate a description link to describe this Node.

        Returns: the created link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        node_link.name = self._name
        if self._desc:
            node_link.msg = self._desc
        for dev in self._devices:
            dev.get_desc_link(node_link)
        return node_link

    def execute(self, node_link):
        """Handle links in node_link to corresponding Devices and executes them.

        Returns: None
        """
        for dev_link in node_link.dev_links:
            try:
                dev = self._devices[dev_link.id]
                dev.execute(dev_link)
            except IndexError:
                self.logger.error(
                    self._fullname, "Wrong device id: {id}".format(id=dev_link.id))
