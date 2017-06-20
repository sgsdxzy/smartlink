import asyncio
from asyncio import wait_for
import serial
from serial_asyncio import open_serial_connection

from smartlink import node


class ReactiveSerialDevice(node.Device):
    """Smartlink device for reactive serial device with the operation mode
    of one response from device for one command to device."""

    def __init__(self, name, write_sep=b'', read_sep=b'', ports=None, timeout=None, loop=None):
        """`ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._write_sep = write_sep
        self._read_sep = read_sep
        self._read_sep_len = len(read_sep)
        self._ports = ports
        self._timeout = timeout
        self._loop = loop or asyncio.get_event_loop()

        self._connected = False
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()

        self._init_smartlink_ports()

    def _init_smartlink_ports(self):
        """Initilize smartlink commands and updates."""
        if self._ports:
            self.add_update("Connection", "bool",
                            lambda: self._connected, grp="")
            port_ext_args = ';'.join(self._ports)
            self.add_command("Connect", "enum", self.connect_to_port,
                             ext_args=port_ext_args, grp="")
            self.add_command("Disconnect", "", self.close_port, grp="")

    async def connect_to_port(self, port_num):
        """Connect to port_num-th port in self._ports."""
        try:
            index = int(port_num)
            await self.open_port(self._ports[index])
        except (ValueError, IndexError):
            self.logger.error(
                self.fullname, "No such port number: {0}".format(port_num))

    async def open_port(self, port, **kargs):
        """Open serial port `port`.
        Returns: True if successful, False otherwise."""
        if self._connected:
            self.logger.error(self.fullname, "Already connected.")
            return False
        try:
            self._reader, self._writer = await wait_for(
                open_serial_connection(url=port, **kargs), timeout=self._timeout)
        except asyncio.TimeoutError:
            self.logger.error(self.fullname, "Connection timeout.")
            return False
        except (OSError, serial.SerialException):
            self.logger.exception(
                self.fullname, "Failed to open port {port}".format(port=port))
            return False
        self._connected = True
        return True

    def close_port(self):
        """Close serial port."""
        if not self._connected:
            # self.logger.error(self.fullname, "Not connected.")
            return
        self._writer.close()
        self._reader = None
        self._writer = None
        self._connected = False

    async def _write(self, cmd):
        """Write cmd to opened port."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        with (await self._lock):
            self._writer.write(cmd + self._write_sep)

    async def _write_and_read(self, cmd):
        """Write cmd to opened port, then await response."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return b""
        with (await self._lock):
            self._writer.write(cmd + self._write_sep)
            try:
                response = await wait_for(self._reader.readuntil(self._read_sep), timeout=self._timeout)
            except asyncio.TimeoutError:
                self.logger.error(self.fullname, "Read timeout.")
                self.close_port()
                return b""
            except asyncio.IncompleteReadError:
                self.logger.error(self.fullname, "Connection lost while reading.")
                self.close_port()
                return b""
            except asyncio.LimitOverrunError:
                self.logger.error(self.fullname, "Read buffer overrun.")
                self.close_port()
                return b""
        if response == b"":
            # Connection is closed
            self.logger.error(self.fullname, "Connection lost.")
            self.close_port()
            return b""
        if self._read_sep_len > 0:
            return response[:-self._read_sep_len]
        else:
            return response
