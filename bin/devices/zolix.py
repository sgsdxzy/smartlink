"""Smartlink device for Zolix SC300 controller."""

import asyncio
from asyncio import ensure_future, wait_for
import serial
from serial_asyncio import create_serial_connection, open_serial_connection

from smartlink import node


class SC300Protocal(asyncio.Protocol):
    """Asyncio protocal for serial communicaton with SC300."""

    def __init__(self, dev):
        super().__init__()
        self._transport = None
        self._buffer = bytearray()
        self._dev = dev
        self.logger = dev.logger

    def connection_made(self, transport):
        self._transport = transport

    def data_received(self, data):
        self._buffer.extend(data)
        start = 0
        while True:
            end = self._buffer.find(b'\r', start)
            if end == -1:
                self._buffer = self._buffer[start:]
                return
            self._dev.handle_response(self._buffer[start:end])
            start = end + 1

    def connection_lost(self, exc):
        if not self._dev.peaceful_disconnect:
            self.logger.error("SC300", "Connection to SC300 is lost.")
        self._dev.close_port()
        self.dev.peaceful_disconnect = True


class SC300(node.Device):
    """Smartlink device for Zolix SC300 controller."""
    X = b'X'
    Y = b'Y'
    Z = b'Z'

    def __init__(self, name="SC300", loop=None):
        super().__init__(name)
        self._loop = loop or asyncio.get_event_loop()
        self._connected = False
        self._verified = False
        self._transport = None
        self._protocal = None
        self._sep = b'\r'   # <CR>
        self._timeout = 5
        self.peaceful_disconnect = False

        # SC300 status
        self._moving = '0'
        self._x = 0
        self._y = 0
        self._z = 0

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self.add_update("Status", "bool", lambda: self._y > 100000)
        self.add_update("Moving", "bool", lambda: self._moving)
        self.add_update("Position", "int", lambda: self._y)
        self.add_command("Open", "", self.open)
        self.add_command("Close", "", lambda: self.zero(self.Y))

    async def open_port(self, port):
        """Open serial port `port`"""
        if self._connected:
            self.logger.error("SC300", "SC300 is already connected.")
            return
        # Serial port characteristcs
        baudrate = 19200
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        protocal = SC300Protocal(self)
        try:
            self._transport, self._protocal = await wait_for(
                create_serial_connection(self._loop, lambda: protocal, port, baudrate=baudrate, bytesize=bytesize,
                                         parity=parity, stopbits=stopbits), timeout=self._timeout)
        except asyncio.TimeoutError:
            self.logger.error("SC300", "Connection timeout.")
            return
        except (OSError, serial.SerialException):
            self.logger.error(
                "SC300", "Failed to open port {port}".format(port=port))
            return
        self._connected = True
        self.peaceful_disconnect = False
        # Identify SC300
        self._verified = False
        self._write(b"VE")

    def close_port(self):
        """Close serial port."""
        if not self._connected:
            self.logger.error("SC300", "Not connected to SC300.")
            return
        self.peaceful_disconnect = True
        self._transport.close()
        self._transport = None
        self._protocal = None
        self._connected = False
        self._verified = False

    def _write(self, cmd):
        """Write cmd and sep to SC300."""
        if not self._connected:
            self.logger.error("SC300", "Not connected to SC300.")
            return
        self._transport.write(cmd)
        self._transport.write(self._sep)

    def handle_response(self, res):
        """Handle response from SC300."""
        if not self._verified:
            if res.find(b"SC300") != -1:
                self._verified = True
                self._write(b"?Y")
                return
            else:
                self.logger.error("SC300", "Connected device is not SC300.")
                self.close_port()
                return
        if res == b"ER":
            self.logger.error("SC300", "Error reported by device.")
            return
        try:
            axis = res[1]
            pos = res[3:]
            if axis == self.X[0]:
                self._x = int(pos)
            elif axis == self.Y[0]:
                self._y = int(pos)
            elif axis == self.Z[0]:
                self._z = int(pos)
            else:
                self.logger.error(
                    "SC300", "Unrecognized response: {0}".format(res.decode()))
            self._moving = '0'
        except (ValueError, IndexError):
            self.logger.error(
                "SC300", "Unrecognized response: {0}".format(res.decode()))

    def zero(self, axis):
        self._write(b'H' + axis)
        self._moving = '1'

    def relative_move(self, axis, n):
        if n > 0:
            self._write(b''.join((b'+', axis, b',', str(n).encode())))
        else:
            self._write(b''.join((b'-', axis, b',', str(-n).encode())))
        self._moving = '1'

    def open(self):
        if self._y < 100000:
            self.relative_move(self.Y, 120000 - self._y)
