import asyncio
from asyncio import ensure_future
import logging
from smartlink.node import Node
from smartlink.nodeserver import NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices.dg645 import DG645
from devices.zolix import SC300


def main():
    node = Node("Laser Room")
    dg645_sl = node.create_device("DG645")
    dg645_dev = DG645(dg645_sl)
    ensure_future(dg645_dev.open_port('COM14'))

    sc300_sl = node.create_device("SC300")
    sc300_dev = SC300(sc300_sl)
    ensure_future(sc300_dev.open_port("COM3"))

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
