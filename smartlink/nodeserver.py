from sys import stdout
from collections import namedtuple
from twisted.internet import protocol, task
from twisted.logger import globalLogBeginner, textFileLogObserver, Logger

from smartlink import link_pb2

logger = Logger()

class SmartlinkControl(protocol.Protocol):
    """Twisted protocal class for smartlink node server to handle connections
        from controls."""
    def __init__(self):
        super().__init__()
        self.client_ready = False

    def connectionMade(self):
        self.factory.clientConnectionMade(self)

    def connectionLost(self, reason=protocol.connectionDone):
        self.factory.clientConnectionLost(self)

    def dataReceived(self, data):
        if not self.client_ready:
            try:
                if data.decode("utf-8") == "RDY":
                    self.client_ready = True
                    self.factory.clientReady(self)
            except:
                # Client didn't send "RDY" to notify that it is ready for broadcast
                pass
            return
        try:
            node_link = link_pb2.NodeLink.FromString(data)
        except:
            logger.warn("{prefix} failed to parse node link from {peer}".\
                format(prefix=self.logPrefix(), peer=self.transport.getPeer()))
            return
        try:
            self.factory.node.exec_node_link(node_link)
        except:
            logger.warn("{prefix} failed to execute operation from {peer}".\
                format(prefix=self.logPrefix(), peer=self.transport.getPeer()))
            #raise

class SmartlinkFactory(protocol.Factory):
    """Twisted factory class for smartlink node server."""
    protocol = SmartlinkControl
    def __init__(self, node, frequency=1):
        self.broadcast = []
        self.node = node
        self.desc_link = node.generate_node_desclink()
        #print(self.desc_link)
        self.str_desc = self.desc_link.SerializeToString()
        self.loopcall = task.LoopingCall(self.announce)
        self.loopcall.start(1/frequency)

    def announce(self):
        """Broadcast node link to all connected and ready controls.
            This is usually used for updating node status.
            """
        node_link = self.node.get_node_link()
        str_link = node_link.SerializeToString()
        #print(len(str_link))
        #print(node_link)
        for client in self.broadcast:
            client.transport.write(str_link)

    def clientConnectionMade(self, client):
        client.transport.write(self.str_desc)

    def clientReady(self, client):
        self.broadcast.append(client)

    def clientConnectionLost(self, client):
        try:
            self.broadcast.remove(client)
        except ValueError:
            # Client lost connection before it is ready
            pass

class Operation:
    """Storing the information of an operation."""
    __slots__ = ['id', 'name', 'desc', 'func', 'args', 'auto']
    def __init__(self, id, name, desc, func, args=None, auto=-1):
        """auto=1 means LoopingCall executes the associated func and get
            update link on every interval. auto=0 disable this. auto=-1 means
            parameter no applicable (for node operation). auto>1 is for internal
            use. auto=2 indicates a oneshot.
            """
        self.id = id
        self.name = name
        self.desc = desc
        self.func = func
        self.args = args
        self.auto = auto

class Device:
    """A node device is the basic unit of operation execution.
        It executes operations in ctrl_oplist to get args and wraps them in a device
        link. This is usually used for generating status update for control.
        It parses incoming operation device links, looks up corresponding methods
        in node_oplist and executes them.
        """
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
        self.ctrl_oplist = []
        self.node_oplist = []
        self.dev_id = None

    def add_ctrl_op(self, name, desc, func, args=None, auto=1):
        """Add one operation to be executed on control. func is the local
            function to generate arguments.  args must be a sequence of strings
            and provides ext_args to generate corresponding widget. if auto is
            0 then LoopingCall does not execute the associated func and get
            update link on every interval.

            Returns: the operation's id.
            """
        op_id = len(self.ctrl_oplist)
        op = Operation(op_id, name, desc, func, args, auto)
        self.ctrl_oplist.append(op)
        return op_id

    def add_ctrl_ops(self, oplist):
        """Add multiple operations to be executed on control. oplist is
            a list of (name, desc, func, args, auto) tuples.

            Returns: None
            """
        for op in oplist:
            self.add_ctrl_op(*op)

    def oneshot(self, op_id):
        """On next LoopingCall interval, execute the associated func of control
            operation with id op_id and send the result to control.

            Returns: None
            """
        if self.ctrl_oplist[op_id].auto == 0:
            self.ctrl_oplist[op_id].auto = 2

    def add_node_op(self, name, desc, func, args=None):
        """Add one operation to be executed on node. func is the local
            function to execute the operation. args must be a sequence of strings
            and provides ext_args to generate corresponding widget.

            Returns: the operation's id.
            """
        op_id = len(self.node_oplist)
        op = Operation(op_id, name, desc, func, args, -1)
        self.node_oplist.append(op)
        return op_id

    def add_node_ops(self, oplist):
        """Add multiple operations to be executed on node. oplist is
            a list of (name, desc, func, args) tuples.
            Returns: None
            """
        for op in oplist:
            self.add_node_op(*op)

    def get_dev_link(self, node_link):
        """Execute operations in ctrl_oplist to get args and wrap them in a
            device link, then append it to node_link.
            Returns: the created link_pb2.DeviceLink
        """
        dev_link = node_link.device_links.add()
        if self.dev_id is not None:
            dev_link.device_id = self.dev_id
        for op in self.ctrl_oplist:
            if op.auto > 0:
                link = dev_link.links.add()
                link.id = op.id
                args = op.func()
                if args is not None:
                    link.args.append(str(args))
            if op.auto == 2: # oneshot
                op.auto = 0
        return dev_link

    def exec_dev_link(self, dev_link):
        """Parse link_pb2.DeviceLink dev_link, looks up corresponding methods
            in node_oplist and executes them.
            Returns: None
            """
        for link in dev_link.links:
            op = self.node_oplist[link.id]
            if len(link.args) > 0:
                op.func(link.args)
            else:
                op.func()

    def generate_dev_desclink(self, node_link):
        """Generate a description device link to describe operations about this
            device, then append it to node_link.
            Returns: the created link_pb2.DeviceLink
            """
        dev_link = node_link.device_links.add()
        if self.dev_id is not None:
            dev_link.device_id = self.dev_id
        dev_link.device_name = self.name
        dev_link.device_desc = self.desc
        for op in self.ctrl_oplist:
            link = dev_link.links.add()
            link.target = link_pb2.Link.CONTROL
            link.id = op.id
            link.name = op.name
            link.desc = op.desc
            if op.args is not None:
                for arg in op.args:
                    link.args.append(str(arg))
        for op in self.node_oplist:
            link = dev_link.links.add()
            link.target = link_pb2.Link.NODE
            link.id = op.id
            link.name = op.name
            link.desc = op.desc
            if op.args is not None:
                for arg in op.args:
                    link.args.append(str(arg))
        return dev_link


class Node:
    """A node in smartlink is the terminal to control physical devices like
        stepper motors. A Node object consists of one or multiple Device objects.
        It is responsible for wrapping device links into a node link, parsing a
        node link and handling contained device links over to corresponding devices.
        """
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
        self.device_list = []

    def add_device(self, device):
        """Add device to node and assign the device its id.
            Returns: None
            """
        dev_id = len(self.device_list)
        device.dev_id = dev_id
        self.device_list.append(device)

    def add_devices(self, device_list):
        """Add a list of devices to node and assign them their id.
            Returns: None
            """
        for dev in device_list:
            self.add_device(dev)

    def get_node_link(self):
        """Get device links from devices and wrap them into a node link.
            Returns: link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        for dev in self.device_list:
            dev.get_dev_link(node_link)
        return node_link

    def exec_node_link(self, node_link):
        """Parse link_pb2.NodeLink node_link and handle contained device links to
            corresponding devices.
            Returns: None
            """
        for dev_link in node_link.device_links:
            dev = self.device_list[dev_link.device_id]
            dev.exec_dev_link(dev_link)

    def generate_node_desclink(self):
        """Generate a description node link to describe devices about this node.
            Returns: link_pb2.NodeLink
            """
        node_link = link_pb2.NodeLink()
        node_link.node_name = self.name
        node_link.node_desc = self.desc
        for dev in self.device_list:
            dev.generate_dev_desclink(node_link)
        return node_link


def start(reactor, factory, port):
    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])
    reactor.listenTCP(port, factory)
    reactor.run()
