import asyncio
import logging
from smartlink.node import Node
from smartlink.nodeserver import NodeServer

global position
position = [0, 0, 0]
inited = [False, False, False]


def get_position(index):
    return position[index]


def set_position(index, args):
    if not inited[index]:
        return
    position[index] = float(args)
    if position[index] > 20:
        position[index] = 20
    elif position[index] < 0:
        position[index] = 0


def is_inited(index):
    return inited[index]


def relative(index, args):
    set_position(index, [str(get_position(index) + float(args[0]))])


def init(index):
    position[index] = 0
    inited[index] = True


def main():
    node = Node("Target")
    std = node.create_device("Stand")
    std.add_update("Position", "float", lambda: get_position(0), grp="X")
    std.add_update("Initialized", "bool", lambda: is_inited(0), grp="X")
    std.add_command("Absolute", "float",
                    lambda args: set_position(0, args), grp="X")
    std.add_command("Initialize", "", lambda: init(0), grp="X")

    std.add_update("Position", "float", lambda: get_position(1), grp="Y")
    std.add_update("Initialized", "bool", lambda: is_inited(1), grp="Y")
    std.add_command("Absolute", "float",
                    lambda args: set_position(1, args), grp="Y")
    std.add_command("Initialize", "", lambda: init(1), grp="Y")

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
