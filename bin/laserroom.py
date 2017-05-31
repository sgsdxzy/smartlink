import asyncio
from smartlink.node import Node
from smartlink.nodeserver import NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices.dg645 import DG645
from devices.zolix import SC300
from devices.uniblitz import VMMD3


def main():
    node = Node("Laser Room")
    ports = ['COM1', 'COM3', 'COM8']

    sc300 = SC300(ports=ports)
    dg645 = DG645(ports=ports)
    vmm = VMMD3(DG645=dg645, ports=ports)

    node.add_device(vmm)
    node.add_device(sc300)
    node.add_device(dg645)

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
