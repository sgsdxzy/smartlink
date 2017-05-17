from twisted.internet import reactor, task
from smartlink import nodeserver

global position
position = [0, 0, 0]
inited = [False, False, False]
def get_position(index):
    return position[index]
def set_position(index, args):
    if not inited[index]:
        return
    position[index] = float(args)
    if position[index]>20:
        position[index] = 20
    elif position[index] <0:
        position[index] = 0
def is_inited(index):
    return inited[index]
def relative(index, args):
    set_position(index, [str(get_position(index)+float(args[0]))])
def init(index):
    position[index] = 0
    inited[index] = True

def main():
    node = nodeserver.Node("Target")
    std = node.create_device("Stand")
    x = std.create_group("X")
    x.create_update("Position", "float", lambda:get_position(0))
    x.create_update("Initialized", "bool", lambda:is_inited(0))
    x.create_command("Absolute", "float", lambda args:set_position(0, args))
    #x.add_command("Relative", "float", lambda args:relative(0, args))
    x.create_command("Initialize", "", lambda args: init(0))

    factory = nodeserver.NodeFactory(node, 0.2)
    nodeserver.start(reactor, factory, 5362)

if __name__ == "__main__":
    main()
