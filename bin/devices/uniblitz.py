"""Smartlink device for Uniblitz Devices."""

import serial

from smartlink import node


class VMMD3(node.Device):
    """Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

    def __init__(self, name="VMM-D3", NO=False, ports=None):
        """`ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._NO = NO   # normally open
        self._ports = ports

        self._connected = False
        self._ser = None

        # VMM-D3 status
        if self._NO:
            # Normally open
            self._ch1 = '1'
            self._ch2 = '1'
            self._ch3 = '1'
        else:
            self._ch1 = '0'
            self._ch2 = '0'
            self._ch3 = '0'

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        if self._ports:
            self.add_update("Connection", "bool", lambda: self._connected, grp="")
            port_ext_args = ';'.join(self._ports)
            self.add_command("Connect", "enum", self.connect_to_port, ext_args=port_ext_args, grp="")
            self.add_command("Disconnect", "", self.close_port, grp="")

        # TODO: full VMM-D3 controls

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
            self.logger.exception(self.fullname, "Failed to open port {port}".format(port=port))
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

    def open_shutter(self, ch):
        if ch == '1':
            if self._NO:
                cmd = b'A'
            else:
                cmd = b'@'
            if self._write(cmd):
                self._ch1 = '1'
        elif ch == '2':
            if self._NO:
                cmd = b'C'
            else:
                cmd = b'B'
            if self._write(cmd):
                self._ch2 = '1'
        elif ch == '3':
            if self._NO:
                cmd = b'E'
            else:
                cmd = b'D'
            if self._write(cmd):
                self._ch3 = '1'
        else:
            self.logger.error(self.fullname, "No such channel: {0}".format(ch))

    def close_shutter(self, ch):
        if ch == '1':
            if self._NO:
                cmd = b'@'
            else:
                cmd = b'A'
            if self._write(cmd):
                self._ch1 = '0'
        elif ch == '2':
            if self._NO:
                cmd = b'B'
            else:
                cmd = b'C'
            if self._write(cmd):
                self._ch2 = '0'
        elif ch == '3':
            if self._NO:
                cmd = b'D'
            else:
                cmd = b'E'
            if self._write(cmd):
                self._ch3 = '0'
        else:
            self.logger.error(self.fullname, "No such channel: {0}".format(ch))
