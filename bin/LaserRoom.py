import asyncio
from smartlink import Node, NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import zolix, uniblitz, SRS, DeviceError


class ShutterSC300(zolix.SC300):
    """SC300 used as laser shutter."""

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        pass

    async def init_device(self):
        await super().init_device()
        await self.zero(self.Y)

    def is_shutter_open(self):
        return self._y > 100000

    async def open_shutter(self):
        if self._y < 100000:
            await self.relative_move(self.Y, 120000 - self._y)

    async def close_shutter(self):
        if self._y > 60000:
            await self.relative_move(self.Y, 0 - self._y)


class SingleShotController(uniblitz.VMMD3):
    """Smartlink device for Uniblitz VMM-D3 Shutter Driver."""

    def __init__(self, dg645, sc300, NO=False, ports=None):
        """`dg645` and `sc300` are the associated DG645 and SC300
        to perform single shot.
        """
        super().__init__(name="Shutter Group", NO=NO, ports=ports)
        self._dg645 = dg645
        self._sc300 = sc300

        # Single shot controls
        self._hardware = True
        self._firing_mode = False

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self.add_update("Mode", "bool", lambda: self._firing_mode, grp="Firing Control")
        self.add_update("Hardware Control", "bool", lambda: self._hardware, grp="Firing Control")
        self.add_command("Enable Hardware Control", "bool", self.enable_hardware, grp="Firing Control")
        self.add_command("Switch Firing Mode", "bool", self.enable_firing_mode, grp="Firing Control")
        self.add_command("FIRE!", "", self.fire_single_shot, grp="Firing Control")

        self.add_update("S-Shutter", "bool", lambda: self._ch1, grp="Shutter")
        self.add_update("M-Shutter", "bool", self._sc300.is_shutter_open, grp="Shutter")
        self.add_update("M-Moving", "bool", lambda: self._sc300._y_moving, grp="Shutter")
        self.add_update("M-Position", "int", lambda: self._sc300._y, grp="Shutter")
        self.add_command("Open", "", self.open_shutter_group, grp="Shutter")
        self.add_command("Close", "", self.close_shutter_group, grp="Shutter")

    def init_device(self):
        """Initilize device after a successful `open_port()`."""
        self.open_shutter(1)

    async def open_shutter_group(self):
        if self._firing_mode:
            await self._sc300.open_shutter()
        else:
            self.close_shutter(1)
            await self._sc300.open_shutter()
            self.open_shutter(1)

    async def close_shutter_group(self):
        if self._firing_mode:
            await self._sc300.close_shutter()
        else:
            self.close_shutter(1)
            await self._sc300.close_shutter()
            self.open_shutter(1)

    def enable_hardware(self, mode):
        self._hardware = mode

    async def enable_firing_mode(self, mode):
        if self._firing_mode is mode:
            return
        if mode:
            if not self._dg645:
                self._log_error("DG645 must be present to perform single shot.")
                raise DeviceError
            if self._dg645._trigger_source != 3:    # Single shot external rising edges
                self._log_error('Trigger mode for DG645 must be set to "Single shot external rising edges".')
                raise DeviceError
            await self._sc300.close_shutter()
            self.close_shutter(1)
            self._firing_mode = True
        else:
            await self._sc300.close_shutter()
            self.open_shutter(1)
            self._firing_mode = False

    async def fire_single_shot(self):
        """User must first open zolix SC300 controlled shutter and put
        DG645 in "3 Single shot external rising edges" trigger mode. This
        method will trigger DG645, open shutter after a laser operation cycle,
        then close it after another laser operation cycle."""
        if not self._firing_mode:
            self._log_error("FIRE is only possible after enabling firing mode.")
            raise DeviceError
        await self._dg645._write(b"*TRG")
        if not self._hardware:
            await asyncio.sleep(0.2)
            self.open_shutter(1)
            await asyncio.sleep(0.2)
            self.close_shutter(1)


def main():
    node = Node("Laser Room")
    # ports = ['COM1', 'COM3', 'COM8']

    sc300 = ShutterSC300()
    dg645 = SRS.DG645()
    vmm = SingleShotController(dg645=dg645, sc300=sc300, NO=False)

    node.add_device(vmm)
    node.add_device(sc300)
    node.add_device(dg645)

    loop = asyncio.get_event_loop()
    vmm.open_port('COM1')
    loop.run_until_complete(sc300.open_port('COM3'))
    loop.run_until_complete(dg645.open_port('COM8'))

    server = NodeServer(node, interval=0.2, loop=loop)
    server.start()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    server.close()
    loop.close()


if __name__ == "__main__":
    main()
