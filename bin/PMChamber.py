import asyncio
from smartlink import Node, NodeServer

import sys
from pathlib import Path  # if you haven't already done so
root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from devices import newport


def main():
    node = Node("Plasma Mirror Chamber")
    # ports = ['COM1', 'COM3', 'COM8']

    xps = newport.XPS(
        group_names=["Group1", "Group2", "Group3", "Group4", "Group5", "Group7"])

    node.add_device(xps)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(xps.open_connection("192.168.254.254", 5001))

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
