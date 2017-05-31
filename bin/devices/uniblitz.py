"""Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

import asyncio
from asyncio import ensure_future

import serial

from smartlink import node


class VMMD3(node.Device):
    """Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

    def __init__(self, name="VMM-D3", DG645=None, ports=None):
        """`DG645` is the associated DG645 to perform single shot.
        `ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._dg645 = DG645
        self._ports = ports

        self._connected = False
        self._ser = None

        # VMM-D3 status
        self._is_open = '1'

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        if self._ports:
            self.add_update("Connection", "bool", lambda: self._connected, grp="")
            port_ext_args = ';'.join(self._ports)
            self.add_command("Connect", "enum", self.connect_to_port, ext_args=port_ext_args, grp="")
            self.add_command("Disconnect", "", self.close_port, grp="")

        self.add_update("Status", "bool", lambda: self._is_open, grp="Shutter")
        self.add_command("Open", "", self.open_shutter, grp="Shutter")
        self.add_command("Close", "", self.close_shutter, grp="Shutter")
        self.add_command("FIRE!", "", self.fire_single_shot, grp="Shutter")

    def connect_to_port(self, port_num):
        """Connect to port_num-th port in self._ports."""
        try:
            index = int(port_num)
            self.open_port(self._ports[index])
        except (ValueError, IndexError):
            self.logger.error(self.fullname, "No such port number: {0}".format(port_num))

    def open_port(self, port):
        if self._connected:
            # self.logger.error(self.fullname, "Already connected.")
            return
        # Serial port characteristcs
        baudrate = 9600
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        try:
            self._ser = serial.Serial(port=port, baudrate=baudrate,
                bytesize=bytesize, parity=parity, stopbits=stopbits)
        except serial.SerialException:
            self.logger.error(self.fullname, "Failed to open port {port}".format(port=port))
            return
        self._connected = True

    def close_port(self):
        if not self._connected:
            # self.logger.error(self.fullname, "Not connected.")
            return
        self._ser.close()
        self._connected = False

    def _write(self, cmd):
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return False
        self._ser.write(cmd)
        return True

    def open_shutter(self):
        # VMM-D3 is put at normally open
        if self._write(b'A'):
            self._is_open = '1'

    def close_shutter(self):
        # VMM-D3 is put at normally open
        if self._write(b'@'):
            self._is_open = '0'

    def fire_single_shot(self):
        """User must first open zolix SC300 controlled shutter and put
        DG645 in "3 Single shot external rising edges" trigger mode. This
        method will trigger DG645, open shutter after a laser operation cycle,
        then close it after another laser operation cycle."""
        if not self._dg645:
            self.logger.error(self.fullname, "No DG645 selected.")
            return
        ensure_future(self._fire_single_shot())

    async def _fire_single_shot(self):
        self.close_shutter()
        await self._dg645._write(b"*TRG")
        await asyncio.sleep(0.2)
        self.open_shutter()
        await asyncio.sleep(0.2)
        self.close_shutter()
