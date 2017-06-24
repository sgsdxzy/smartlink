"""This module defines the physical structure of a node."""
import os
import sys
import traceback
import asyncio
from datetime import date, datetime

from .common import DeviceError, args_to_sequence
from .link_pb2 import Link, NodeLink


class Logger:
    """A non-persistent object-level logger"""
    __slots__ = ["_datefmt", "_fmt", "_filename", "_file", "_buffer"]
    datefmt = '%Y-%m-%d %H:%M:%S'
    fmt = "[{source}:{level}]\t{asctime}\t{name}:\t{message}\n{exc}"

    def __init__(self, datefmt=None, fmt=None, filename=None, logbuffer=None):
        self._datefmt = datefmt or Logger.datefmt
        self._fmt = fmt or Logger.fmt
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

    def info(self, name, message, source="NODE", verbose=True, local=True, remote=False):
        """Print the message. If verbose is True, print it to stdout;
        if local is True, log it to file; if remote is True,
        append it to logbuffer to be sent over network."""
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="INFO", name=name, message=message, exc="")
        if verbose:
            print(record, end="")
        if local and self._file:
            self._file.write(record)
        if remote and self._buffer is not None:
            self._buffer.append(record)

    def warning(self, name, message, source="NODE", verbose=True, local=False, remote=True):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="WARNING", name=name, message=message, exc="")
        if verbose:
            print(record, end="")
        if local and self._file:
            self._file.write(record)
        if remote and self._buffer is not None:
            self._buffer.append(record)

    def error(self, name, message, source="NODE", verbose=True, local=False, remote=True):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="ERROR", name=name, message=message, exc="")
        if verbose:
            print(record, end="")
        if local and self._file:
            self._file.write(record)
        if remote and self._buffer is not None:
            self._buffer.append(record)

    def exception(self, name, message, source="NODE", verbose=True, local=False, remote=True):
        time = datetime.today().strftime(self._datefmt)
        record = self._fmt.format(
            asctime=time, source=source, level="EXCEPTION", name=name, message=message, exc=traceback.format_exc())
        if verbose:
            print(record, end="")
        if local and self._file:
            self._file.write(record)
        if remote and self._buffer is not None:
            self._buffer.append(record)


class Command:
    """Command is the type of operation sent by control to be executed on node."""
    __slots__ = ["_dev", "id", "name", "grp", "_fullname",
                 "_sigs", "_func", "_is_coro", "_ext_args", "_logger"]

    def __init__(self, dev, id_, name, sigs, func, ext_args=None, grp=""):
        self._dev = dev
        self.id = id_
        self.name = name
        self.grp = grp
        if sigs:
            self._sigs = list(args_to_sequence(sigs))
        else:
            self._sigs = []
        self._func = func
        if asyncio.iscoroutinefunction(func):
            self._is_coro = True
        else:
            self._is_coro = False
        if ext_args:
            self._ext_args = list(args_to_sequence(ext_args))
        else:
            self._ext_args = []
        self._logger = None
        self._fullname = None

    def init_logger(self):
        self._logger = self._dev._logger
        if self.grp:
            self._fullname = '.'.join(
                (self._dev._fullname, self.grp, self.name))
        else:
            self._fullname = '.'.join((self._dev._fullname, self.name))

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    def _parse_args(self, args):
        """Convert the sequence of string in args to their corrsponding types
        according to sigs.

        Retruns: a generator sequence of arguments.
        """
        for sig, arg in zip(self._sigs, args):
            if sig == "int" or sig == "enum":
                yield int(arg)
            elif sig == "float":
                yield float(arg)
            elif sig == "bool":
                if arg == "0":
                    yield False
                elif arg == "1":
                    yield True
                else:
                    raise ValueError("Invalid boolean value: {0}".format(arg))
            elif sig == "str":
                yield arg
            else:
                raise NotImplementedError("Unsupported signature type: {0}".format(sig))

    async def _exec_func(self, args):
        """Wrapper to execute coroutine func."""
        try:
            comp_args = self._parse_args(args)
            await self._func(*comp_args)
            self._log_info("Executed with arguments: {args}".format(args=' '.join(args)))
        except DeviceError:
            # The concrete error is already logged.
            msg = "Failed to execute with arguments: {args}".format(args=' '.join(args))
            self._log_error(msg, verbose=True, local=True, remote=True)
        except Exception:
            msg = "Failed to execute with arguments: {args}".format(args=' '.join(args))
            self._log_exception(msg)
            self._log_error(msg, verbose=False, local=True, remote=False)

    def execute(self, link):
        """Call the associated func. If the func is a coroutine, it will be ensure_futured"""
        args = link.args
        if self._is_coro:
            asyncio.ensure_future(self._exec_func(args))
        else:
            try:
                comp_args = self._parse_args(args)
                self._func(*comp_args)
                self._log_info("Executed with arguments: {args}".format(args=' '.join(args)))
            except DeviceError:
                # The concrete error is already logged.
                msg = "Failed to execute with arguments: {args}".format(args=' '.join(args))
                self._log_error(msg, verbose=True, local=True, remote=True)
            except Exception:
                msg = "Failed to execute with arguments: {args}".format(args=' '.join(args))
                self._log_exception(msg)
                self._log_error(msg, verbose=False, local=True, remote=False)

    def get_desc(self, dev_link):
        """Generate a description link to describe this Command, then append it to dev_link.

        Returns: the created Link
        """
        link = dev_link.links.add()
        link.type = Link.COMMAND
        link.id = self.id
        link.name = self.name
        link.group = self.grp
        link.sigs.extend(self._sigs)
        link.args.extend(self._ext_args)
        return link


class Update:
    """Update is the type of operation executed on node to display the result on
    control.
    """
    __slots__ = ["_dev", "id", "name", "grp", "_fullname",
                 "_sigs", "_func", "_ext_args", "_logger", "_old"]

    def __init__(self, dev, id_, name, sigs, func, ext_args=None, grp=""):
        self._dev = dev
        self.id = id_
        self.name = name
        self.grp = grp
        if sigs:
            self._sigs = list(args_to_sequence(sigs))
        else:
            self._sigs = []
        self._func = func
        if ext_args:
            self._ext_args = list(args_to_sequence(ext_args))
        else:
            self._ext_args = []
        self._logger = None
        self._fullname = None

        self._old = None

    def init_logger(self):
        self._logger = self._dev._logger
        if self.grp:
            self._fullname = '.'.join(
                (self._dev._fullname, self.grp, self.name))
        else:
            self._fullname = '.'.join((self._dev._fullname, self.name))

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    def get_update(self, dev_link):
        """Execute the associated func and if the result is different from old,
        wrap the result in a Link and append it to dev_link.

        Returns: the created Link if has new result or None
        """
        try:
            new = self._func()
            if self._sigs:
                # Only send the update if signature is non-empty
                if new == self._old or None:
                    return None
                else:
                    self._old = new
                    link = dev_link.links.add()
                    link.id = self.id
                    link.args.extend(args_to_sequence(new))
                    return link
            else:
                return None
        except Exception:
            self._log_exception("Failed to update.")

    def get_full_update(self, dev_link):
        """Execute the associated func, wrap the result in a Link and
        append it to dev_link.

        Returns: the created Link or None if empty
        """
        try:
            new = self._func()
            if self._sigs:
                # Only send the update if signature is non-empty
                link = dev_link.links.add()
                link.id = self.id
                link.args.extend(args_to_sequence(new))
                return link
            else:
                return None
        except Exception:
            self._log_exception("Failed to update.")

    def get_desc(self, dev_link):
        """Generate a description link to describe this Update, then append it to dev_link.

        Returns: the created Link or None is signature is empty
        """
        if self._sigs:
            # Only send the update if signature is non-empty
            link = dev_link.links.add()
            link.type = Link.UPDATE
            link.id = self.id
            link.name = self.name
            link.group = self.grp
            link.sigs.extend(self._sigs)
            link.args.extend(self._ext_args)
            return link
        else:
            return None


class Device:
    """A Device is the programming correspondence to a physical device. It may
    contain one or more OperationGroups. An OperationGroup is a group of
    interrelated Commands or Updates whose generated UI on control should be
    grouped together. Device is the basic unit for configuration saving/loading
    and logging.
    """

    def __init__(self, name):
        self.name = name
        self.id = None
        self._node = None
        self._fullname = name
        self._logger = None

        self._groups = [""]
        self._commands = []
        self._updates = []

    def init_logger(self):
        self._logger = self._node._logger
        self._fullname = '.'.join((self._node._fullname, self.name))
        for cmd in self._commands:
            cmd.init_logger()
        for update in self._updates:
            update.init_logger()

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    def add_group(self, name):
        """Create a new OperationGroup with name."""
        self._groups.append(name)

    def add_command(self, name, sigs, func, ext_args=None, grp=""):
        """Create a new Command and add it to group `grp`. If the group does not
        exist, it will be created first.

        Returns: the created Command.
        """
        if grp not in self._groups:
            self._groups.append(grp)
        id_ = len(self._commands)
        cmd = Command(self, id_, name, sigs, func, ext_args, grp)
        self._commands.append(cmd)
        return cmd

    def add_update(self, name, sigs, func, ext_args=None, grp=""):
        """Create a new Update and add it to group `grp`. If the group does not
        exist, it will be created first.

        Returns: the created Update.
        """
        if grp not in self._groups:
            self._groups.append(grp)
        id_ = len(self._updates)
        update = Update(self, id_, name, sigs, func, ext_args, grp)
        self._updates.append(update)
        return update

    def get_update(self, node_link):
        """Get updates, wrap them in a DeviceLink, then append them to node_link.

        Returns: the created DeviceLink or None if empty
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id
        for update in self._updates:
            update.get_update(dev_link)
        if not dev_link.links:  # empty
            del node_link.dev_links[-1]
            return None
        return dev_link

    def get_full_update(self, node_link):
        """Get full updates, wrap them in a DeviceLink, then append them to node_link.

        Returns: the created DeviceLink or None if empty
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id
        for update in self._updates:
            update.get_full_update(dev_link)
        if not dev_link.links:  # empty
            del node_link.dev_links[-1]
            return None
        return dev_link

    def get_desc(self, node_link):
        """Generate a description link to describe this Device, then
        append it to node_link.

        Returns: the created DeviceLink or None if empty
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id
        dev_link.name = self.name
        dev_link.groups.extend(self._groups)
        for update in self._updates:
            update.get_desc(dev_link)
        for cmd in self._commands:
            cmd.get_desc(dev_link)
        if not dev_link.links:  # empty
            del node_link.dev_links[-1]
            return None
        return dev_link

    def execute(self, dev_link):
        """Handle links in dev_link to corresponding Commands and executes them.

        Returns: None
        """
        for link in dev_link.links:
            try:
                cmd = self._commands[link.id]
                cmd.execute(link)
            except IndexError:
                self._log_error("Wrong command id: {id}".format(id=link.id))


class Node:
    """A Node in smartlink corresponds to a network terminal, usually a computer,
     to control physical devices. A Node consists of one or multiple Devices.
    Node is the basic unit of network communication with control.
    """

    def __init__(self, name):
        self.name = name
        self._devices = []

        # Logs go to three handlers:
        #   1. All logs are printed to stdout
        #   2. Info logs about executed commands are logged to file
        #   3. Error logs are sent to Control through update link
        pdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        logfile = os.path.join(
            pdir, "log", "{name}-{date}{ext}".format(name=name, date=str(date.today()), ext='.log'))
        os.makedirs(os.path.join(pdir, 'log'), exist_ok=True)
        self._fullname = name
        self._log_buffer = []
        self._logger = Logger(filename=logfile, logbuffer=self._log_buffer)

    def _log_info(self, msg, **kargs):
        self._logger.info(self._fullname, msg, **kargs)

    def _log_warning(self, msg, **kargs):
        self._logger.warning(self._fullname, msg, **kargs)

    def _log_error(self, msg, **kargs):
        self._logger.error(self._fullname, msg, **kargs)

    def _log_exception(self, msg, **kargs):
        self._logger.exception(self._fullname, msg, **kargs)

    def close(self):
        """Safely close this node object and free its resources.

        Returns: None
        """
        self._logger.close()

    def clear_log(self):
        """Clear all log entries. This method should be called by nodeserver
        when log has been successfully sent."""
        self._log_buffer.clear()

    def add_device(self, dev):
        """Added device `dev` to this node."""
        dev._node = self
        id_ = len(self._devices)
        dev.id = id_
        dev.init_logger()
        self._devices.append(dev)

    def get_update_link(self):
        """Get updates from devices and wrap them in a NodeLink.

        Returns: the created NodeLink
        """
        node_link = NodeLink()
        for dev in self._devices:
            dev.get_update(node_link)
        node_link.logs.extend(self._log_buffer)
        return node_link

    def get_full_update_link(self):
        """Get full updates from devices and wrap them in a NodeLink.

        Returns: the created NodeLink
        """
        node_link = NodeLink()
        for dev in self._devices:
            dev.get_full_update(node_link)
        return node_link

    def get_desc_link(self):
        """Generate a description link to describe this Node.

        Returns: the created NodeLink
        """
        node_link = NodeLink()
        node_link.name = self.name
        for dev in self._devices:
            dev.get_desc(node_link)
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
                self._log_error("Wrong device id: {id}".format(id=dev_link.id))
