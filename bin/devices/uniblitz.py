"""Smartlink device for Uniblitz Devices."""

import serial

from . import Device, DeviceError


class VMMD3(Device):
    """Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

    def __init__(self, name="VMM-D3", NO=False, ports=None):
        """`ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._ports = ports
        self._ser_property = {"baudrate": 9600,
            "bytesize": serial.EIGHTBITS,
            "stopbits": serial.STOPBITS_ONE,
            "parity": serial.PARITY_NONE,
            "rtscts": False}

        self._NO = NO   # normally open
        self._connected = False
        self._ser = None

        # VMM-D3 status
        if self._NO:
            # Normally open
            self._ch1 = True
            self._ch2 = True
            self._ch3 = True
        else:
            self._ch1 = False
            self._ch2 = False
            self._ch3 = False

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

    def connect_to_port(self, port_num):
        """Connect to port_num-th port in self._ports."""
        try:
            index = int(port_num)
            self.open_port(self._ports[index])
        except (ValueError, IndexError):
            self._log_error("No such port number: {0}".format(port_num))
            raise DeviceError

    def open_port(self, port):
        """Open serial port `port`."""
        if self._connected:
            self._log_warning("Already connected.")
            return
        try:
            self._ser = serial.Serial(port=port, **self._ser_property)
        except (OSError, serial.SerialException):
            self._log_exception("Failed to open port {port}".format(port=port))
            raise DeviceError
        self._connected = True
        self.init_device()

    def init_device(self):
        """Initilize device after a successful `open_port()`."""
        pass

    def close_port(self):
        if not self._connected:
            return
        if self._ser is not None:
            self._ser.close()
            self._ser = None
        self._connected = False

    def _write(self, cmd):
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError
        self._ser.write(cmd)

    def open_shutter(self, ch):
        if ch == 1:
            if self._NO:
                cmd = b'A'
            else:
                cmd = b'@'
            self._write(cmd)
            self._ch1 = True
        elif ch == 2:
            if self._NO:
                cmd = b'C'
            else:
                cmd = b'B'
            self._write(cmd)
            self._ch2 = True
        elif ch == 3:
            if self._NO:
                cmd = b'E'
            else:
                cmd = b'D'
            self._write(cmd)
            self._ch3 = True
        else:
            self._log_error("No such channel: {0}".format(str(ch)))
            raise DeviceError

    def close_shutter(self, ch):
        if ch == 1:
            if self._NO:
                cmd = b'@'
            else:
                cmd = b'A'
            self._write(cmd)
            self._ch1 = False
        elif ch == 2:
            if self._NO:
                cmd = b'B'
            else:
                cmd = b'C'
            self._write(cmd)
            self._ch2 = False
        elif ch == 3:
            if self._NO:
                cmd = b'D'
            else:
                cmd = b'E'
            self._write(cmd)
            self._ch3 = False
        else:
            self._log_error("No such channel: {0}".format(str(ch)))
            raise DeviceError
