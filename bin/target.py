from twisted.internet import reactor
from twisted.logger import Logger
from smartlink import nodeserver

global position
position = [-1]
def get_position():
    return [str(position[0])]
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
    node.addDevice("X", "X axis stepper motor", [("POS", get_position)],\
        [("MOVE",set_position, '0', '20'), \
        ("RELATIVE", relative_position), \
        ("INIT", init_x)])

    factory = nodeserver.SmartlinkFactory(1, Logger(), node.ctrlOpHandler, node.nodeOpHandler, node.nodeDesc)
    nodeserver.start(reactor, factory, 5362)

if __name__ == "__main__":
    main()
