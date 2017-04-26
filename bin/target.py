from twisted.internet import reactor
from twisted.logger import Logger
from smartlink import nodeserver
from smartlink import smartlink_pb2 as pb2

global position
position = [-1]
def get_position():
    return str(position[0])
def set_position(pos):
    position[0] = float(pos[0])
    if position[0]>20:
        position[0] = 20
    elif position[0] <0:
        position[0] = 0
def relative_position(pos):
    position[0] += float(pos[0])
    if position[0]>20:
        position[0] = 20
    elif position[0] <0:
        position[0] = 0
def init_x():
    posiiton[0] = 0

def main():
    node = nodeserver.Node("Target", "Target stand")
    node.addDevice("X", "X axis stepper motor", \
        [("MOVE",set_position, '0', '20'), \
        ("RELATIVE", relative_position), \
        ("INIT", init_x)], \
        [get_position])

    factory = nodeserver.SmartlinkFactory(5, Logger(), node.operationHandler, node.updateHandler, node.nodeDescription)
    nodeserver.start(reactor, factory, 5362)

if __name__ == "__main__":
    main()
