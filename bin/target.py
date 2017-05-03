from twisted.internet import reactor
from smartlink import nodeserver

global position
position = [-1, -1, -1]
def get_position(index):
    return position[index]
def set_position(index, args):
    position[index] = float(args[0])
    if position[index]>20:
        position[index] = 20
    elif position[index] <0:
        position[index] = 0
def init(index):
    position[index] = 0

def main():
    node = nodeserver.Node("Target", "Target stand")
    x_st = nodeserver.Device("X", "X axis stepper motor")
    x_st.add_ctrl_op("Position", "float", lambda:get_position(0))
    x_st.add_node_op("Move", "float", lambda args:set_position(0, args))
    x_st.add_node_op("Initialize", "", lambda:init(0))
    y_st = nodeserver.Device("Y", "Y axis stepper motor")
    y_st.add_ctrl_op("Position", "float", lambda:get_position(1))
    y_st.add_ctrl_op("In", "bool", lambda:abs(get_position(1)-10)<1)
    y_st.add_node_op("Move", "float", lambda args:set_position(1, args), [10])
    z_st = nodeserver.Device("Z", "Z axis stepper motor")
    z_st.add_ctrl_op("Position", "float", lambda:get_position(2))
    z_st.add_ctrl_op("In", "bool", lambda:abs(get_position(2)-10)<1)
    z_st.add_node_op("Move", "float", lambda args:set_position(2, args))
    #y_st.add_node_op("INIT", "", lambda args:init(1))
    node.add_devices([x_st, y_st, z_st])

    factory = nodeserver.SmartlinkFactory(node, 1)
    nodeserver.start(reactor, factory, 5362)

if __name__ == "__main__":
    main()
