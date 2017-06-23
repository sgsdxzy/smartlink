"""Smartlink device for Alicat Digital Flow Controllers."""

import asyncio
from asyncio import ensure_future, wait_for
from concurrent.futures import CancelledError
import serial
from serial_asyncio import open_serial_connection

from smartlink import node


class PCD(node.Device):
    """Smartlink device for Alicat PCD Digital Flow Controllers."""

    def __init__(self, name="PCD", address=b'A', ports=None, loop=None):
        """`ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._address = address
        self._ports = ports
        self._loop = loop or asyncio.get_event_loop()
        self._timeout = None

        self._connected = False
        self._reader = None
        self._writer = None
        self._handle_res_task = None

        # PCD states
        self._pressure = b'0'
        self._set_point = b'0'

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
        self.add_update("Pressure", "float", lambda: self._pressure, grp="Flow Control")
        self.add_update("Set-point", "float", lambda: self._set_point, grp="Flow Control")
        self.add_command("Set", "float", self.set_pressure, grp="Flow Control")

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
            # self.logger.error(self.fullname, "DG645 is already connected.")
            return
        # Serial port characteristcs
        baudrate = 19200
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        rtscts = False
        try:
            self._reader, self._writer = await wait_for(
                open_serial_connection(url=port, baudrate=baudrate, bytesize=bytesize,
                                       parity=parity, stopbits=stopbits, rtscts=rtscts), timeout=self._timeout)
        except asyncio.TimeoutError:
            self.logger.error(self.fullname, "Connection timeout.")
            return
        except (OSError, serial.SerialException):
            self.logger.exception(
                self.fullname, "Failed to open port {port}".format(port=port))
            return
        self._connected = True

        # Enable streaming mode
        self._write(b"*@=A")
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
        """Write cmd to PCD."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        self._writer.write(cmd + b'\r')

    async def _read(self):
        """Read response from PCD."""
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
        """Handle response from PCD."""
        try:
            while True:
                res = await self._read()
                try:
                    _, self._pressure, self._set_point = res.split(b' ')
                except ValueError:
                    self.logger.error(
                        self.fullname, "Unrecognized response: {0}".format(res.decode()))
        except CancelledError:
            return

    def set_pressure(self, pressure):
        """Set the pressure set-point."""
        pressure = pressure.encode()
        cmd = b"%cS%s" % (self._address, pressure)
        self._write(cmd)
