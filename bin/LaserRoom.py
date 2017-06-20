import asyncio
from asyncio import ensure_future
from smartlink.node import Node
from smartlink.nodeserver import NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import zolix, uniblitz, SRS


class ShutterSC300(zolix.SC300):
    """SC300 used as laser shutter."""

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        self.add_update("M-Shutter", "bool", self.is_shutter_open, grp="Shutter")
        self.add_update("Moving", "bool", lambda: self._moving, grp="Shutter")
        self.add_update("Position", "int", lambda: self._y, grp="Shutter")

    async def open_port(self, port, **kargs):
        """Open serial port `port`.
        Returns: True if successful, False otherwise."""
        # Serial port characteristcs
        success = await super().open_port(port)
        if not success:
            return False
        await self.zero(self.Y)
        return True

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

    def __init__(self, dg645, sc300, ports=None):
        """`dg645` and `sc300` are the associated DG645 and SC300
        to perform single shot.
        """
        super().__init__(name="Shutter Group", NO=True, ports=ports)
        self._dg645 = dg645
        self._sc300 = sc300
        self._ports = ports

        # Single shot controls
        self._firing_mode = '0'

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        if self._ports:
            self.add_update("Connection", "bool",
                            lambda: self._connected, grp="")
            port_ext_args = ';'.join(self._ports)
            self.add_command("Connect", "enum", self.connect_to_port,
                             ext_args=port_ext_args, grp="")
            self.add_command("Disconnect", "", self.close_port, grp="")

        self.add_update(
            "Mode", "bool", lambda: self._firing_mode, grp="FIRING CONTROL")
        self.add_command("Switch Firing Mode", "bool",
                         self.enable_firing_mode, grp="FIRING CONTROL")
        self.add_command("FIRE!", "", self.fire_single_shot,
                         grp="FIRING CONTROL")

        self.add_update("S-Shutter", "bool", lambda: self._ch1, grp="Shutter")
        self.add_command("Open", "", self.open_shutter_group, grp="Shutter")
        self.add_command("Close", "", self.close_shutter_group, grp="Shutter")

    async def open_shutter_group(self):
        if self._firing_mode == '1':
            await self._sc300.open_shutter()
            return
        self.close_shutter('1')
        await self._sc300.open_shutter()
        self.open_shutter('1')

    async def close_shutter_group(self):
        if self._firing_mode == '1':
            await self._sc300.close_shutter()
            return
        self.close_shutter('1')
        await self._sc300.close_shutter()
        self.open_shutter('1')

    async def enable_firing_mode(self, mode):
        if self._firing_mode == mode:
            return
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return

        if mode == '1':
            if not self._dg645:
                self.logger.error(
                    self.fullname, "DG645 must be present to perform single shot.")
                return
            if self._dg645._trigger_source != 3:    # Single shot external rising edges
                self.logger.error(self.fullname,
                                  'Trigger mode for DG645 must be set to "Single shot external rising edges".')
                return
            await self._sc300.close_shutter()
            self.close_shutter('1')
            self._firing_mode = '1'
        elif mode == '0':
            await self._sc300.close_shutter()
            self.open_shutter('1')
            self._firing_mode = '0'
        else:
            self.logger.error(
                self.fullname, "Unrecognized boolean value: {0}".format(mode))
            return

    async def fire_single_shot(self):
        """User must first open zolix SC300 controlled shutter and put
        DG645 in "3 Single shot external rising edges" trigger mode. This
        method will trigger DG645, open shutter after a laser operation cycle,
        then close it after another laser operation cycle."""
        if self._firing_mode != '1':
            self.logger.error(
                self.fullname, "FIRE is only possible after enabling firing mode.")
            return
        await self._dg645._write(b"*TRG")
        await asyncio.sleep(0.2)
        self.open_shutter('1')
        await asyncio.sleep(0.2)
        self.close_shutter('1')


def main():
    node = Node("Laser Room")
    # ports = ['COM1', 'COM3', 'COM8']

    sc300 = ShutterSC300()
    dg645 = SRS.DG645()
    vmm = SingleShotController(dg645=dg645, sc300=sc300)

    node.add_device(vmm)
    node.add_device(sc300)
    node.add_device(dg645)

    vmm.open_port('COM1')
    ensure_future(sc300.open_port('COM3'))
    ensure_future(dg645.open_port('COM8'))

    loop = asyncio.get_event_loop()
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
