"""Smartlink device for Stanford Research Systems."""

import asyncio
from asyncio import ensure_future, wait_for
import serial
from serial_asyncio import open_serial_connection

from smartlink import node


class DG645(node.Device):
    """Smartlink device for DG645 Digital Delay Generator."""

    def __init__(self, name="DG645", ports=None, loop=None):
        """`ports` is a list of avaliable port names. If it is None, no serial
        connection management is provided on panel."""
        super().__init__(name)
        self._ports = ports
        self._loop = loop or asyncio.get_event_loop()

        self._connected = False
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()
        self._sep = b'\r'   # <CR>
        self._timeout = 5
        # Wait for this seconds after a set command to exectute get command
        self._wait_interval = 0.05

        # DG645 states
        self._delays = {}
        for i in range(10):
            self._delays[i] = [0, 0]
        self._trigger_source = 0
        self._prescale = 1
        self._advt = b'0'

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        if self._ports:
            self.add_update("Connection", "bool", lambda: self._connected, grp="")
            port_ext_args = ';'.join(self._ports)
            self.add_command("Connect", "enum", self.connect_to_port, ext_args=port_ext_args, grp="")
            self.add_command("Disconnect", "", self.close_port, grp="")

        self.add_update("Current Trigger Source", "enum", lambda: self._trigger_source,
            ("0 Internal;1 External rising edges;2 External falling edges;"
            "3 Single shot external rising edges;4 Single shot external falling edges;"
            "5 Single shot;6 Line"), grp="Trigger")
        self.add_command("Set Trigger Source", "enum", self.set_trigger_source,
            ("0 Internal;1 External rising edges;2 External falling edges;"
            "3 Single shot external rising edges;4 Single shot external falling edges;"
            "5 Single shot;6 Line"), grp="Trigger")
        self.add_command("Trigger", "", self.trigger, grp="Trigger")
        self.add_update("Prescale Factor", "int", lambda: self._prescale, grp="Prescale")
        self.add_update("Advanced Triggering", "bool", lambda: self._advt, grp="Prescale")
        self.add_command("Set Prescale Factor",
                              "int", self.set_prescale_factor, grp="Prescale")
        self.add_command("Set Advanced Triggering", "bool", self.set_advt, grp="Prescale")

        self.add_update("A", ["enum", "float"], lambda: self._delays[2],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self.add_update("B", ["enum", "float"], lambda: self._delays[3],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self.add_command("A", ["enum", "float"], lambda d, t: self.set_delay('2', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self.add_command("B", ["enum", "float"], lambda d, t: self.set_delay('3', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")

        self.add_update("C", ["enum", "float"], lambda: self._delays[4],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="CD")
        self.add_update("D", ["enum", "float"], lambda: self._delays[5],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="CD")
        self.add_command("C", ["enum", "float"], lambda d, t: self.set_delay('4', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="CD")
        self.add_command("D", ["enum", "float"], lambda d, t: self.set_delay('5', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="CD")

        self.add_update("E", ["enum", "float"], lambda: self._delays[6],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="EF")
        self.add_update("F", ["enum", "float"], lambda: self._delays[7],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="EF")
        self.add_command("E", ["enum", "float"], lambda d, t: self.set_delay('6', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="EF")
        self.add_command("F", ["enum", "float"], lambda d, t: self.set_delay('7', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="EF")

        self.add_update("G", ["enum", "float"], lambda: self._delays[8],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="GH")
        self.add_update("H", ["enum", "float"], lambda: self._delays[9],
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="GH")
        self.add_command("G", ["enum", "float"], lambda d, t: self.set_delay('8', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="GH")
        self.add_command("H", ["enum", "float"], lambda d, t: self.set_delay('9', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="GH")

    def connect_to_port(self, port_num):
        """Connect to port_num-th port in self._ports."""
        try:
            index = int(port_num)
            ensure_future(self.open_port(self._ports[index]))
        except (ValueError, IndexError):
            self.logger.error(self.fullname, "No such port number: {0}".format(port_num))

    async def open_port(self, port):
        """Open serial port `port`"""
        if self._connected:
            # self.logger.error(self.fullname, "DG645 is already connected.")
            return
        # Serial port characteristcs
        baudrate = 9600
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        rtscts = True
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
        # Identify DG645
        res = await self._write_and_read(b"*IDN?")
        if res.find(b"DG645") == -1:
            self.logger.error(self.fullname, "Connected device is not DG645.")
            self.close_port()
            return
        # Reset defaults
        await self._write(b"*RST")

        await self._get_initial_update()

    async def _get_initial_update(self):
        # Initial state update
        await self.get_trigger_source()
        await self.get_advt()
        await self.get_prescale_factor()
        await self.get_delays()

    def close_port(self):
        """Close serial port."""
        if not self._connected:
            # self.logger.error(self.fullname, "Not connected.")
            return
        self._writer.close()
        self._reader = None
        self._writer = None
        self._connected = False

    def reset(self):
        """Reset DG645 to factory default settings."""
        ensure_future(self._write(b"*RST"))

    async def _write(self, cmd):
        """Write cmd to opened port."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        with (await self._lock):
            self._writer.write(cmd)
            self._writer.write(self._sep)

    async def _write_and_read(self, cmd):
        """Write cmd to opened port, then await response."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return b""
        with (await self._lock):
            self._writer.write(cmd)
            self._writer.write(self._sep)
            try:
                response = await wait_for(self._reader.readuntil(b"\r\n"), timeout=self._timeout)
            except asyncio.TimeoutError:
                self.logger.error(self.fullname, "Read timeout.")
                self.close_port()
                return b""
        if response == b"":
            # Connection is closed
            self.logger.error(self.fullname, "Connection lost.")
            self.close_port()
            return b""
        return response[:-2]

    def trigger(self):
        """When the DG645 is configured for single shot triggers, this command initiates a
        single trigger. When it is configured for externally triggered single shots, this
        command arms the DG645 to trigger on the next detected external trigger. """
        ensure_future(self._write(b"*TRG"))

    async def get_advt(self):
        """Query the advanced triggering enable register. If i is '0', advanced
        triggering is disabled. If i is '1' advanced triggering is enabled. """
        res = (await self._write_and_read(b"ADVT?"))
        if res == b'0':
            self._advt = b'0'
        elif res == b'1':
            self._advt = b'1'
        else:
            self.logger.error(self.fullname, "Unrecognized response: {0}".format(res))

    async def set_advt(self, i):
        """Set the advanced triggering enable register. If i is '0', advanced
        triggering is disabled. If i is '1' advanced triggering is enabled. """
        await self._write(b"ADVT %c" % i.encode())
        await asyncio.sleep(self._wait_interval)
        await self.get_advt()

    async def get_prescale_factor(self):
        """Query the prescale factor for Trigger input."""
        res = (await self._write_and_read(b"PRES?0"))
        try:
            self._prescale = int(res)
        except ValueError:
            self.logger.error(self.fullname, "Unrecognized response: {0}".format(res))

    async def set_prescale_factor(self, i):
        """Set the prescale factor for Trigger input."""
        await self._write(b"PRES 0,%c" % i.encode())
        await asyncio.sleep(self._wait_interval)
        await self.get_prescale_factor()

    async def get_trigger_source(self):
        """Query the current trigger source."""
        res = (await self._write_and_read(b"TSRC?"))
        try:
            self._trigger_source = int(res)
        except ValueError:
            self.logger.error(self.fullname, "Unrecognized response: {0}".format(res))

    async def set_trigger_source(self, i):
        """Set the trigger source to i.
            0 Internal
            1 External rising edges
            2 External falling edges
            3 Single shot external rising edges
            4 Single shot external falling edges
            5 Single shot
            6 Line
        """
        await self._write(b"TSRC %c" % i.encode())
        await asyncio.sleep(self._wait_interval)
        await self.get_trigger_source()

    async def get_delays(self):
        """Query the delay for all channels."""
        for i in range(10):
            res = await self._write_and_read(b"DLAY?%c" % str(i).encode())
            try:
                ch, delay = res.split(b',')
                self.delays[int(ch)] = float(delay)
            except ValueError:
                self.logger.error(self.fullname, "Unrecognized response: {0}".format(res))

    def set_delay(self, c, d, t):
        """Set the delay for channel c to t relative to channel d."""
        ensure_future(self._set_delay(c, d, t))

    async def _set_delay(self, c, d, t):
        """Set the delay for channel c to t relative to channel d."""
        c = c.encode()
        d = d.encode()
        t = t.encode()
        await self._write(b'DLAY %c,%c,%s' % (c, d, t))
        await asyncio.sleep(self._wait_interval)
        res = await self._write_and_read(b"DLAY?%c" % c)
        try:
            ch, delay = res.split(b',')
            self.delays[int(ch)] = float(delay)
        except ValueError:
            self.logger.error(self.fullname, "Unrecognized response: {0}".format(res))
