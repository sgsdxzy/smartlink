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
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    sthandler = logging.StreamHandler()
    logger.addHandler(sthandler)

    node = Node("Target")
    std = node.create_device("Stand")
    x = std.create_group("X")
    x.create_update("Position", "float", lambda: get_position(0))
    x.create_update("Initialized", "bool", lambda: is_inited(0))
    x.create_command("Absolute", "float", lambda args: set_position(0, args))
    #x.add_command("Relative", "float", lambda args:relative(0, args))
    x.create_command("Initialize", "", lambda args: init(0))
    y = std.create_group("Y")
    y.create_update("Position", "float", lambda: get_position(1))
    y.create_update("Initialized", "bool", lambda: is_inited(1))
    y.create_command("Absolute", "float", lambda args: set_position(1, args))
    #x.add_command("Relative", "float", lambda args:relative(0, args))
    y.create_command("Initialize", "", lambda args: init(1))

    loop = asyncio.get_event_loop()
    server = NodeServer(node, interval=0.5, loop=loop)
    server.start()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    server.close()
    loop.close()


if __name__ == "__main__":
    main()
