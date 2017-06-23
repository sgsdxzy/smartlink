import asyncio
from asyncio import ensure_future
from smartlink import Node, NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import newport


class BSXPS(newport.XPS):
    """Limit the range of Group5."""
    def __init__(self, *args):
        super().__init__(group_names=["Group1", "Group2", "Group3", "Group4", "Group5"], *args)

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        # self.add_update("Backlash Compensation", "float", lambda: self._comp_amount, grp="")
        self.add_command("Backlash Compensation", "float", self.set_comp_amount, grp="")
        self.add_command("Enable", "bool", self.set_backlash, grp="")
        self.add_command("Initialize All", "", self.initialize_all, grp="")
        self.add_command("Home All", "", self.home_all, grp="")
        self.add_command("Kill All", "", self.kill_all, grp="")

        for i in range(self._group_num - 1):    # Remove direct control of Group5
            group_name = self._group_names[i]
            self.add_update("Positon", "float",
                lambda i=i: self._group_positions[i], grp=group_name)
            self.add_update("Status", "Int",
                lambda i=i: self._group_status[i], grp=group_name)
            self.add_command("Absolute move", "float",
                lambda pos, i=i: ensure_future(self.absolute_move(i, pos)), grp=group_name)
            self.add_command("Relative move", "float",
                lambda pos, i=i: ensure_future(self.relative_move(i, pos)), grp=group_name)
            self.add_command("Relative move", "float",
                lambda pos, i=i: ensure_future(self.relative_move(i, pos)), grp=group_name)
        # Group5
        i = 4
        group_name = self._group_names[i]
        self.add_update("Positon", "float",
            lambda i=i: self._group_positions[i], grp=group_name)
        self.add_update("Status", "Int",
            lambda i=i: self._group_status[i], grp=group_name)
        self.add_update("Main", "bool",
            lambda i=i: self._group_positions[i] == 30, grp=group_name)
        self.add_update("Sim", "bool",
            lambda i=i: self._group_positions[i] == -150, grp=group_name)
        self.add_command("Enable Main", "",
            lambda i=i: ensure_future(self.absolute_move(i, "30")), grp=group_name)
        self.add_command("Enable Sim", "",
            lambda i=i: ensure_future(self.absolute_move(i, "-150")), grp=group_name)


def main():
    node = Node("Beam Splitter Chamber")
    # ports = ['COM1', 'COM3', 'COM8']

    xps = BSXPS()

    node.add_device(xps)

    ensure_future(xps.open_connection("192.168.254.254", 5001))

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
