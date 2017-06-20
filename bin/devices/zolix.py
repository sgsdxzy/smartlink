"""Smartlink device for Zolix Devices."""

import serial

import sys
from pathlib import Path
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import ReactiveSerialDevice


class SC300(ReactiveSerialDevice):
    """Smartlink device for Zolix SC300 controller."""
    X = b'X'
    Y = b'Y'
    Z = b'Z'

    def __init__(self, name="SC300", ports=None):
        super().__init__(name, b'\r', b'\r', ports, 30)

        # SC300 status
        self._moving = '0'
        self._x = 0
        self._y = 0
        self._z = 0

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        # TODO: SC300 controls
        pass

    async def open_port(self, port, **kargs):
        """Open serial port `port`.
        Returns: True if successful, False otherwise."""
        # Serial port characteristcs
        baudrate = 19200
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        success = await super().open_port(port, baudrate=baudrate, bytesize=bytesize,
                               parity=parity, stopbits=stopbits)
        if not success:
            return False

        # Identify SC300
        res = await self._write_and_read(b"VE")
        if res.find(b"SC300") == -1:
            self.logger.error(self.fullname, "Connected device is not SC300.")
            self.close_port()
            return False
        return True

    def _handle_response(self, res):
        """Handle response from SC300."""
        if res == b"ER":
            self.logger.error(self.fullname, "Error reported by device.")
            return
        try:
            axis = res[1:2]
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

    async def zero(self, axis):
        self._moving = '1'
        res = await self._write_and_read(b'H' + axis)
        self._handle_response(res)

    async def relative_move(self, axis, n):
        self._moving = '1'
        if n > 0:
            cmd = b"+%c,%s" % (axis, str(n).encode())
        else:
            cmd = b"-%c,%s" % (axis, str(-n).encode())
        res = await self._write_and_read(cmd)
        self._handle_response(res)
