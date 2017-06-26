"""Smartlink device for Alicat Digital Flow Controllers."""

import asyncio
from asyncio import ensure_future
from concurrent.futures import CancelledError
import serial

from . import ReactiveSerialDevice, DeviceError


class PCD(ReactiveSerialDevice):
    """Smartlink device for Alicat PCD Digital Flow Controllers."""

    def __init__(self, name="PCD", address='A', query_interval=0.2, ports=None):
        ser_property = {"baudrate": 19200,
            "bytesize": serial.EIGHTBITS,
            "stopbits": serial.STOPBITS_ONE,
            "parity": serial.PARITY_NONE,
            "rtscts": False}
        super().__init__(name, b'\r', b'\r', ports, 5, ser_property)

        # PCD states
        self._address = address
        self._query_interval = query_interval
        self._pressure = 0
        self._set_point = 0
        self._query_task = None

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self.add_update("Pressure", "float", lambda: self._pressure, grp="Flow Control")
        self.add_update("Set-point", "float", lambda: self._set_point, grp="Flow Control")
        self.add_command("Set", "float", self.set_pressure, grp="Flow Control")

    async def init_device(self):
        # Disable streaming mode
        self._write(b"*@=A")
        self._query_task = ensure_future(self._query())

    def close_port(self):
        if self._query_task is not None:
            self._query_task.cancel()
            self._query_task = None
        super().close_port()

    async def _query(self):
        try:
            cmd = self._address.encode()
            while True:
                res = await self._write_and_read(cmd)
                self._handle_response(res)
                await asyncio.sleep(self._query_interval)
        except CancelledError:
            return
        except Exception:
            self._log_exception("Failed to query device status.")
            self.close_port()

    def _handle_response(self, res):
        """Handle response from PCD."""
        res = res.decode()
        try:
            address, pressure, set_point = res.split(' ')
            if address == self._address:
                self._pressure = float(pressure)
                self._set_point = float(set_point)
        except ValueError:
            self._log_error("Unrecognized response: {0}".format(res))
            raise DeviceError

    async def set_pressure(self, pressure):
        """Set the pressure set-point."""
        cmd = "{address}S{pressure:.2f}".format(address=self._address, pressure=pressure)
        res = await self._write_and_read(cmd.encode())
        self._handle_response(res)
