"""Smartlink device for Zolix Devices."""

import asyncio
from asyncio import ensure_future, wait_for
from concurrent.futures import CancelledError
import serial
from serial_asyncio import open_serial_connection

from smartlink import node


class SC300(node.Device):
    """Smartlink device for Zolix SC300 controller."""
    X = b'X'
    Y = b'Y'
    Z = b'Z'

    def __init__(self, name="SC300", ports=None, loop=None):
        super().__init__(name)
        self._ports = ports
        self._loop = loop or asyncio.get_event_loop()

        self._connected = False
        self._reader = None
        self._writer = None
        self._handle_res_task = None
        self._sep = b'\r'   # <CR>
        self._timeout = 30

        # SC300 status
        self._moving = '0'
        self._x = 0
        self._y = 0
        self._z = 0

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        if self._ports:
            self.add_update("Connection", "bool",
                            lambda: self._connected, grp="")
            port_ext_args = ';'.join(self._ports)
            self.add_command("Connect", "enum", self.connect_to_port,
                             ext_args=port_ext_args, grp="")
            self.add_command("Disconnect", "", self.close_port, grp="")

    def connect_to_port(self, port_num):
        """Connect to port_num-th port in self._ports."""
        try:
            index = int(port_num)
            ensure_future(self.open_port(self._ports[index]))
        except (ValueError, IndexError):
            self.logger.error(
                self.fullname, "No such port number: {0}".format(port_num))

    async def open_port(self, port):
        """Open serial port `port`"""
        if self._connected:
            # self.logger.error(self.fullname, "Already connected.")
            return
        # Serial port characteristcs
        baudrate = 19200
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        try:
            self._reader, self._writer = await wait_for(
                open_serial_connection(url=port, baudrate=baudrate, bytesize=bytesize,
                                       parity=parity, stopbits=stopbits), timeout=self._timeout)
        except asyncio.TimeoutError:
            self.logger.error(self.fullname, "Connection timeout.")
            return
        except (OSError, serial.SerialException):
            self.logger.exception(
                self.fullname, "Failed to open port {port}".format(port=port))
            return
        self._connected = True

        # Identify SC300
        self._write(b"VE")
        res = await self._read()
        if res.find(b"SC300") == -1:
            self.logger.error(
                self.fullname, "Connected device is not SC300.")
            self.close_port()
            return
        self._handle_res_task = ensure_future(self._handle_response())

    def close_port(self):
        """Close serial port."""
        if not self._connected:
            # self.logger.error(self.fullname, "Not connected.")
            return
        self._connected = False
        if self._handle_res_task is not None:
            self._handle_res_task.cancel()
            self._handle_res_task = None
        self._writer.close()
        self._reader = None
        self._writer = None

    def _write(self, cmd):
        """Write cmd and sep to SC300."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        self._writer.write(cmd)
        self._writer.write(self._sep)

    async def _read(self):
        """Read response from SC300."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return b""
        try:
            response = await wait_for(self._reader.readuntil(b"\r"), timeout=self._timeout)
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
        return response[:-1]

    async def handle_response(self, res):
        """Handle response from SC300."""
        try:
            while True:
                res = await self._read()
                if res == b"ER":
                    self.logger.error(self.fullname, "Error reported by device.")
                    continue
                try:
                    axis = res[1]
                    pos = res[3:]
                    if axis == self.X:
                        self._x = int(pos)
                    elif axis == self.Y:
                        self._y = int(pos)
                    elif axis == self.Z:
                        self._z = int(pos)
                    else:
                        self.logger.error(
                            self.fullname, "Unrecognized response: {0}".format(res.decode()))
                    self._moving = '0'
                except (ValueError, IndexError):
                    self.logger.error(
                        self.fullname, "Unrecognized response: {0}".format(res.decode()))
        except CancelledError:
            return

    def zero(self, axis):
        self._write(b'H' + axis)
        self._moving = '1'

    def relative_move(self, axis, n):
        if n > 0:
            self._write(b''.join((b'+', axis, b',', str(n).encode())))
        else:
            self._write(b''.join((b'-', axis, b',', str(-n).encode())))
        self._moving = '1'
