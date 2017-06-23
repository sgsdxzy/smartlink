import asyncio
from asyncio import ensure_future
from smartlink import Node, NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import alicat


def main():
    node = Node("Flow Control Comupter")
    # ports = ['COM1', 'COM3', 'COM8']

    pcd = alicat.PCD()
    node.add_device(pcd)
    ensure_future(pcd.open_port('COM4'))

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
