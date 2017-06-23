import asyncio
from asyncio import wait_for
import serial
from serial_asyncio import open_serial_connection

from smartlink import StreamReadWriter, Device, DeviceError


class ReactiveSerialDevice(Device):
    """Smartlink device for reactive serial device with the operation mode
    of one response from device for one command to device."""

    def __init__(self, name, write_sep=b'\r', read_sep=b'\r', ports=None,
      timeout=None, ser_property={}, loop=None):
        """`ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._write_sep = write_sep
        self._read_sep = read_sep
        self._read_sep_len = len(read_sep)
        self._ports = ports
        self._timeout = timeout
        self._ser_property = ser_property
        self._loop = loop or asyncio.get_event_loop()

        self._connected = False
        self._readwriter = None
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
            self._log_error("No such port number: {0}".format(port_num))
            raise DeviceError

    async def open_port(self, port):
        """Open serial port `port`."""
        if self._connected:
            self._log_warning("Already connected.")
            return
        try:
            self._readwriter = StreamReadWriter(await wait_for(
                open_serial_connection(url=port, **self._ser_property), timeout=self._timeout))
        except asyncio.TimeoutError:
            self._log_error("Connection timeout.")
            raise DeviceError
        except (OSError, serial.SerialException):
            self._log_exception("Failed to open port {port}".format(port=port))
            raise DeviceError
        self._connected = True
        await self.init_device()

    async def init_device(self):
        """Initilize device after a successful `open_port()`."""
        pass

    def close_port(self):
        """Close serial port."""
        if not self._connected:
            return
        if self._readwriter is not None:
            self._readwriter.close()
            self._readwriter = None
        self._connected = False

    async def _write(self, cmd):
        """Write cmd to opened port."""
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError
        with (await self._lock):
            self._readwriter.write(cmd + self._write_sep)

    async def _force_write(self, cmd):
        """Write cmd to opened port without acquiring lock first."""
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError
        if self._lock.locked():
            self._log_warning("Forcing another write while waiting for response.")
        self._readwriter.write(cmd + self._write_sep)

    async def _write_and_read(self, cmd):
        """Write cmd to opened port, then await response."""
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError
        with (await self._lock):
            # clear reader buffer, bypassing StreamReader encapsulation.
            if len(self._readwriter.reader._buffer) > 0:
                self._log_warning("Discarded non-empty device buffer.")
                self._readwriter.reader._buffer.clear()

            self._readwriter.write(cmd + self._write_sep)
            try:
                response = await wait_for(self._reader.readuntil(self._read_sep), timeout=self._timeout)
            except asyncio.TimeoutError:
                self._log_error("Read timeout.")
                self.close_port()
                raise DeviceError
            except asyncio.IncompleteReadError:
                self._log_error("Lost connection to device.")
                self.close_port()
                raise DeviceError
            except asyncio.LimitOverrunError:
                self._log_error("Read buffer overrun.")
                self.close_port()
                raise DeviceError
        return response[:-self._read_sep_len]
