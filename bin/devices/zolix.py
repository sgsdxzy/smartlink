"""Smartlink device for Zolix Devices."""

import serial

import sys
from pathlib import Path
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import ReactiveSerialDevice, DeviceError


class SC300(ReactiveSerialDevice):
    """Smartlink device for Zolix SC300 controller."""
    X = b'X'
    Y = b'Y'
    Z = b'Z'

    def __init__(self, name="SC300", ports=None):
        ser_property = {"baudrate": 19200,
            "bytesize": serial.EIGHTBITS,
            "stopbits": serial.STOPBITS_ONE,
            "parity": serial.PARITY_NONE,
            "rtscts": False}
        super().__init__(name, b'\r', b'\r', ports, 30, ser_property)

        # SC300 status
        self._x_moving = False
        self._y_moving = False
        self._z_moving = False
        self._x = 0
        self._y = 0
        self._z = 0

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        # TODO: SC300 controls
        pass

    async def init_device(self):
        # Identify SC300
        res = await self._write_and_read(b"VE")
        if res.find(b"SC300") == -1:
            self._log_error("Connected device is not SC300.")
            self.close_port()
            raise DeviceError

    def _handle_response(self, res):
        """Handle response from SC300."""
        if res == b"ER":
            self._log_error("Error reported by device.")
            raise DeviceError
        try:
            axis = res[1:2]
            pos = res[3:]
            if axis == self.X:
                self._x = int(pos)
                self._x_moving = False
            elif axis == self.Y:
                self._y = int(pos)
                self._y_moving = False
            elif axis == self.Z:
                self._z = int(pos)
                self._z_moving = False
            else:
                self._log_error("Unrecognized response: {0}".format(res.decode()))
                raise DeviceError
        except (ValueError, IndexError):
            self._log_error("Unrecognized response: {0}".format(res.decode()))
            raise DeviceError

    async def zero(self, axis):
        if axis == self.X:
            self._x_moving = True
        elif axis == self.Y:
            self._y_moving = True
        elif axis == self.Z:
            self._z_moving = True
        else:
            self._log_error("No such axis: {0}".format(axis.decode()))
            raise DeviceError
        res = await self._write_and_read(b'H' + axis)
        self._handle_response(res)

    async def relative_move(self, axis, n):
        if axis == self.X:
            self._x_moving = True
        elif axis == self.Y:
            self._y_moving = True
        elif axis == self.Z:
            self._z_moving = True
        else:
            self._log_error("No such axis: {0}".format(axis.decode()))
            raise DeviceError
        if n > 0:
            cmd = b"+%c,%s" % (axis, str(n).encode())
        else:
            cmd = b"-%c,%s" % (axis, str(-n).encode())
        res = await self._write_and_read(cmd)
        self._handle_response(res)
