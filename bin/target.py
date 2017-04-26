from twisted.internet import reactor
from twisted.logger import Logger
from smartlink import nodeserver, smartlink_pb2

def get_position():
    return position[0]

def set_position(pos):
    position[0] = float(pos[0])

def relative_position(pos):
    position[0] += float(pos[0])

def main():
    global position
    position = [0]
    X_operations = {"moveto" : set_position, "relative" : relative_position}
    devices = {"X" : X_operations}
    factory = nodeserver.SmartlinkFactory(1, Logger(), devices, get_position)
    nodeserver.start(reactor, factory, 5362)

if __name__ == "__main__":
    main()
