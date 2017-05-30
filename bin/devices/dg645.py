"""Smartlink device for DG645 Digital Delay Generator."""

import asyncio
from asyncio import ensure_future, wait_for
import serial
from serial_asyncio import open_serial_connection

from smartlink import node

class DG645(node.Device):
    """Smartlink device for DG645 Digital Delay Generator."""

    def __init__(self, name="DG645"):
        super().__init__(name)
        self._connected = False
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()
        self._sep = b'\r'   # <CR>
        self._timeout = 5
        # Wait for this seconds after a set command to exectute get command
        self._wait_interval = 0.1

        # DG645 states
        self._delays = {}
        for i in range(10):
            self._delays[i] = [b'0', b'0']
        self._prescale = b'1'
        self._advt = b'0'

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self.add_update("Prescale Factor", "int", lambda: self._prescale)
        self.add_update("Advanced Triggering", "bool", lambda: self._advt)
        self.add_command("Set Prescale Factor",
                              "int", self.set_prescale_factor)
        self.add_command("Set Advanced Triggering", "bool", self.set_advt)
        self.add_command("Set Trigger Source", "enum", self.set_trigger_source,
                              ("0 Internal;1 External rising edges;2 External falling edges;"
                               "3 Single shot external rising edges;4 Single shot external falling edges;"
                               "5 Single shot;6 Line"))
        self.add_command("Trigger", "", self.trigger)

        self.add_update("A", ["enum", "float"], lambda: self._delays[2], [
                             "T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self.add_update("B", ["enum", "float"], lambda: self._delays[3], [
                             "T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self.add_command("A", ["enum", "float"], lambda d, t: self.set_delay('2', d, t),
                              ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self.add_command("B", ["enum", "float"], lambda d, t: self.set_delay('3', d, t),
                              ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")

    async def open_port(self, port):
        """Open serial port `port`"""
        if self._connected:
            self.logger.error("DG645", "DG645 is already connected.")
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
            self.logger.error("DG645", "Connection timeout.")
            return
        except (OSError, serial.SerialException):
            self.logger.error(
                "DG645", "Failed to open port {port}".format(port=port))
            return
        self._connected = True
        # Identify DG645
        res = await self._write_and_read(b"*IDN?")
        if res.find(b"DG645") == -1:
            self.logger.error("DG645", "Connected device is not DG645.")
            self.close_port()
            return
        # Reset defaults
        await self._write(b"*RST")

        await self._get_initial_update()

    async def _get_initial_update(self):
        # Initial state update
        await self.get_advt()
        await self.get_prescale_factor()
        await self.get_delays()

    def close_port(self):
        """Close serial port."""
        if not self._connected:
            self.logger.error("DG645", "Not connected to DG645.")
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
            self.logger.error("DG645", "Not connected to DG645.")
            return
        with (await self._lock):
            self._writer.write(cmd)
            self._writer.write(self._sep)

    async def _write_and_read(self, cmd):
        """Write cmd to opened port, then await response."""
        if not self._connected:
            self.logger.error("DG645", "Not connected to DG645.")
            return b""
        with (await self._lock):
            self._writer.write(cmd)
            self._writer.write(self._sep)
            try:
                response = await wait_for(self._reader.readuntil(b"\r\n"), timeout=self._timeout)
            except asyncio.TimeoutError:
                self.logger.error("DG645", "Read timeout.")
                self.close_port()
                return b""
        if response == b"":
            # Connection is closed
            self.logger.error("DG645", "Connection to DG645 is lost.")
            self.close_port()
        return response[:-2]

    def trigger(self):
        """When the DG645 is configured for single shot triggers, this command initiates a
        single trigger. When it is configured for externally triggered single shots, this
        command arms the DG645 to trigger on the next detected external trigger. """
        ensure_future(self._write(b"*TRG"))

    async def get_advt(self):
        """Query the advanced triggering enable register. If i is '0', advanced
        triggering is disabled. If i is '1' advanced triggering is enabled. """
        self._advt = (await self._write_and_read(b"ADVT?"))

    async def set_advt(self, i):
        """Set the advanced triggering enable register. If i is '0', advanced
        triggering is disabled. If i is '1' advanced triggering is enabled. """
        await self._write(b"ADVT " + i.encode())
        await asyncio.sleep(self._wait_interval)
        await self.get_advt()

    async def get_prescale_factor(self):
        """Query the prescale factor for Trigger input."""
        self._prescale = (await self._write_and_read(b'PRES?0'))

    async def set_prescale_factor(self, i):
        """Set the prescale factor for Trigger input."""
        await self._write(b"PRES 0," + i.encode())
        await asyncio.sleep(self._wait_interval)
        await self.get_prescale_factor()

    def set_trigger_source(self, i):
        """Set the trigger source to i.
            0 Internal
            1 External rising edges
            2 External falling edges
            3 Single shot external rising edges
            4 Single shot external falling edges
            5 Single shot
            6 Line
        """
        ensure_future(self._write(b"TSRC " + i.encode()))

    async def get_delays(self):
        """Query the delay for all channels."""
        for i in range(10):
            res = await self._write_and_read(b"DLAY?" + str(i).encode())
            self._delays[i] = res.split(b',')

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
            if delay[0] == b'+':
                self._delays[int(c)] = [ch, delay[1:]]
            else:
                self._delays[int(c)] = [ch, delay]
        except (ValueError, IndexError):
            self.logger.error(
                "DG645", "Failed to parse delay settings from device.")
