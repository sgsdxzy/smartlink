"""Smartlink device for DG645 Digital Delay Generator."""

import asyncio
from asyncio import ensure_future, wait_for
import serial
from serial_asyncio import open_serial_connection


class DG645:
    """Smartlink device for DG645 Digital Delay Generator."""

    def __init__(self, dev):
        """dev is the smartlink device created by node.create_device()"""
        self._dev = dev
        self.logger = dev.logger
        self._connected = False
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()
        self._sep = b'\r'   # <CR>
        self._wait_interval = 0.2   # Wait for this seconds after a set command to exectute get command

        # DG645 states
        self._delays = {}
        for i in range(10):
            self._delays[i] = ['0', '0']
        self._prescale = '1'
        self._advt = '0'

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self._dev.add_update("Prescale Factor", "int", lambda: self._prescale)
        self._dev.add_update("Advanced Triggering", "bool", lambda: self._advt)
        self._dev.add_command("Set Prescale Factor", "int", self.set_prescale_factor)
        self._dev.add_command("Set Advanced Triggering", "bool", self.set_advt)
        self._dev.add_command("Set Trigger Source", "enum", self.set_trigger_source,
            ("0 Internal;1 External rising edges;2 External falling edges;"
            "3 Single shot external rising edges;4 Single shot external falling edges;"
            "5 Single shot;6 Line"))
        self._dev.add_command("Trigger", "", self.trigger)

        self._dev.add_update("T0", ["enum", "float"], lambda: self._delays[0], ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="T0")
        self._dev.add_update("T1", ["enum", "float"], lambda: self._delays[1], ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="T0")

        self._dev.add_update("A", ["enum", "float"], lambda: self._delays[2], ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self._dev.add_update("B", ["enum", "float"], lambda: self._delays[3], ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self._dev.add_command("A", ["enum", "float"], lambda d, t: self.set_delay('2', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")
        self._dev.add_command("B", ["enum", "float"], lambda d, t: self.set_delay('3', d, t),
            ["T0;T1;A;B;C;D;E;F;G;H", ""], grp="AB")

    async def open_port(self, port):
        """Open serial port `port`"""
        # Serial port characteristcs
        baudrate = 9600
        bytesize = serial.EIGHTBITS
        stopbits = serial.STOPBITS_ONE
        parity = serial.PARITY_NONE
        rtscts = True
        try:
            self._reader, self._writer = await wait_for(open_serial_connection(port=port, baudrate=baudrate, bytesize=bytesize,
                                                      parity=parity, stopbits=stopbits, rtscts=rtscts), timeout=5)
        except asyncio.TimeoutError:
            self.logger.error("DG645", "Connection timeout.")
            return
        self._connected = True
        # Identify DG645
        res = await self._write_and_read(b"*IDN?")
        if res.find(b"DG645") == -1:
            self.logger.error("DG645", "Connected device is not DG645.")
            self.close()
            return
        # Reset defaults
        await self._write(b"*RST")

        await self._get_initial_update()

    async def _get_initial_update(self):
        # Initial state update
        await self._get_advt()
        await self._get_prescale_factor()
        await self._get_delays()

    def close(self):
        """Close serial port."""
        if self._connected:
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
                response = await wait_for(self._reader.read(), timeout=5)
            except asyncio.TimeoutError:
                self.logger.error("DG645", "Read timeout.")
                self.close()
                return b""
        if response == b"":
            # Connection is closed
            self.logger.error("DG645", "Connection to DG645 is lost.")
            self.close()
        return response

    def trigger(self):
        """When the DG645 is configured for single shot triggers, this command initiates a
        single trigger. When it is configured for externally triggered single shots, this
        command arms the DG645 to trigger on the next detected external trigger. """
        ensure_future(self._write(b"*TRG"))

    def set_advt(self, i):
        """Set the advanced triggering enable register. If i is '0', advanced
        triggering is disabled. If i is '1' advanced triggering is enabled. """
        ensure_future(self._set_get_advt(i))

    def get_advt(self):
        """Query the advanced triggering enable register. If i is '0', advanced
        triggering is disabled. If i is '1' advanced triggering is enabled. """
        ensure_future(self._get_advt())

    async def _get_advt(self):
        self._advt = await self._write_and_read(b"ADVT?")

    async def _set_get_advt(self, i):
        await self._write(b"ADVT "+i.encode('ascii'))
        await asyncio.sleep(self._wait_interval)
        self._advt = await self._write_and_read(b"ADVT?")

    def get_prescale_factor(self):
        """Query the prescale factor for Trigger input."""

    async def _get_prescale_factor(self):
        self._prescale = await self._write_and_read(b'PRES?0')

    def set_prescale_factor(self, i):
        """Set the prescale factor for Trigger input."""
        ensure_future(self._set_get_prescale_factor(i))

    async def _set_get_prescale_factor(self, i):
        await self._write(b"PRES 0,"+i.encode('ascii'))
        await asyncio.sleep(self._wait_interval)
        self._prescale = await self._write_and_read(b'PRES?0')

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
        ensure_future(self._write(b"TSRC "+i.encode('ascii')))

    def get_delays(self):
        """Query the delay for all channels."""
        ensure_future(self._get_delays())

    async def _get_delays(self):
        """Query the delay for all channels."""
        for i in range(10):
            res = await self._write_and_read(b"DLAY?"+str(i).encode('ascii'))
            self._delays[i] = res.split(b',')

    def set_delay(self, c, d, t):
        """Set the delay for channel c to t relative to channel d."""
        ensure_future(self._set_get_delay(c, d, t))

    async def _set_get_delay(self, c, d, t):
        c = c.encode('ascii')
        d = d.encode('ascii')
        t = t.encode('ascii')
        await self._write(b"DLAY "+c+b','+d+b','+t)
        await asyncio.sleep(self._wait_interval)
        res = await self._write_and_read(b"DLAY?"+c)
        self._delays[int(c)] = res.split(b',')
