"""Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

import serial

class VMMD3:
    """Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

    def __init__(self, dev):
        """dev is the smartlink device created by node.create_device()"""
        self._dev = dev
        self.logger = dev.logger
        self._connected = False
        self._ser = None

        # VMM-D3 status
        self._is_open = '1'

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self._dev.add_update("Status", "bool", lambda: self._is_open)
        self._dev.add_command("Open", "", self.open_shutter)
        self._dev.add_command("Close", "", self.close_shutter)

    def open_port(self, port):
        if self._connected:
            self.logger.error("VMM-D3", "VMM-D3 is already connected.")
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
            self.logger.error("VMM-D3", "Failed to open port {port}".format(port=port))
            return
        self._connected = True

    def close_port(self):
        if not self._connected:
            self.logger.error("VMM-D3", "Not connected to VMM-D3.")
            return
        self._ser.close()
        self._connected = False

    def _write(self, cmd):
        if not self._connected:
            self.logger.error("VMM-D3", "Not connected to VMM-D3.")
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
