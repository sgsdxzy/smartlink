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

                    # Send a full link
                    node_link = self.factory.node.get_full_link()
                    str_link = node_link.SerializeToString()
                    self.transport.write(str_link)

                    # Ready for broadcast
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
            self.factory.node.execute(node_link)
        except:
            logger.warn("{prefix} failed to execute operation from {peer}".\
                format(prefix=self.logPrefix(), peer=self.transport.getPeer()))
            raise

class SmartlinkFactory(protocol.Factory):
    """Twisted factory class for smartlink node server."""
    protocol = SmartlinkControl
    def __init__(self, node, frequency=1):
        self.broadcast = []
        self.node = node
        self.desc_link = node.get_desc_link()
        #print(self.desc_link)
        self.str_desc = self.desc_link.SerializeToString()
        self.loopcall = task.LoopingCall(self.announce)
        self.loopcall.start(1/frequency)

    def announce(self):
        """Broadcast node link to all connected and ready controls.
            This is usually used for updating node status.
            """
        node_link = self.node.get_link()
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

class Command:
    """Command is the type of operation sent by control to be executed on node."""

    def __init__(self, name, sig, func, ext_args=None):
        self.id = -1
        self.name = name
        self.sig = sig
        self.func = func
        self.ext_args = ext_args

    def execute(self, link):
        """Call the associated func and return the result."""
        return self.func(link.data)

    def get_desc_link(self, grp_link):
        """Generate a description link to describe this Command, then append it to grp_link.

        Returns: the created link_pb2.Link
        """
        link = grp_link.links.add()
        link.type = link_pb2.Link.COMMAND
        link.id = self.id
        link.name = self.name
        link.sig = self.sig
        if self.ext_args is not None:
            link.data = self.ext_args

class Update:
    """Update is the type of operation executed on node to display the result on
    control.
    """

    def __init__(self, name, sig, func, ext_args=None):
        self.id = -1
        self.name = name
        self.sig = sig
        self.func = func
        self.ext_args = ext_args
        self.old = None

    def get_link(grp_link):
        """Execute the associated func and if the result is different from prev,
        wrap the result in a link_pb2.Link and append it to grp_link.

        Returns: the created link_pb2.Link if has new result or None
        """
        new = self.func()
        if new == self.old:
            return None
        else:
            self.old = new
            if isinstance(new, tuple):
                #func() returns multiple results
                new = ';'.join(str(result) for result in new)
            else:
                new = str(new)

            link = grp_link.links.add()
            link.id = self.id
            link.data = new
            return link

    def get_full_link(grp_link):
        """Execute the associated func, wrap the result in a link_pb2.Link and
        append it to grp_link.

        Returns: the created link_pb2.Link
        """
        new = self.func()
        if isinstance(new, tuple):
            #func() returns multiple results
            new = ';'.join(str(result) for result in new)
        else:
            new = str(new)

        link = grp_link.links.add()
        link.id = self.id
        link.data = new
        return link

    def get_desc_link(grp_link):
        """Generate a description link to describe this Update, then append it to grp_link.

        Returns: the created link_pb2.Link
        """
        link = grp_link.links.add()
        link.type = link_pb2.Link.UPDATE
        link.id = self.id
        link.name = self.name
        link.sig = self.sig
        if self.ext_args is not None:
            link.args = self.ext_args


class OperationGroup:
    """An OperationGroup is a group of interrelated Commands or Updates whose
    generated UI on control should be grouped together.
    """

    def __init__(self, name, desc=None):
        self.id = -1
        self.name = name
        self.desc = desc
        self.commands = []
        self.updates = []

    def add_command(self, command):
        """Add a Command to this group and assign the Command its id.

        Returns: assigned id
        """
        cmd_id = len(self.commands)
        command.id = cmd_id
        self.commands.append(command)
        return cmd_id

    def add_update(self, update):
        """Add an Update to this group and assign the Update its id.

        Returns: assigned id
        """
        update_id = len(self.updates)
        update.id = update_id
        self.updates.append(update)
        return update_id

    def get_link(self, dev_link):
        """Get updates from the list of Updates, wrap them in a GroupLink, then
        append them to dev_link.

        Returns: the created link_pb2.GroupLink
        """
        grp_link = dev_link.grp_links.add()
        for update in self.updates:
            update.get_link(grp_link)
        if len(grp_link.links) > 0:
            grp_link.id = self.id
        return grp_link

    def get_full_link(self, dev_link):
        """Get full updates from the list of Updates, wrap them in a GroupLink,
        then append them to dev_link.

        Returns: the created link_pb2.GroupLink
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self.id
        for update in self.updates:
            update.get_link(grp_link)
        return grp_link

    def get_desc_link(self, dev_link):
        """Generate a description link to describe this OperationGroup, then
        append it to dev_link.

        Returns: the created link_pb2.GroupLink
        """
        grp_link = dev_link.grp_links.add()
        grp_link.id = self.id
        grp_link.name = self.name
        grp_link.desc = self.desc
        for update in self.updates:
            update.get_desc_link(grp_link)
        for cmd in self.commands:
            cmd.get_desc_link(grp_link)
        return grp_link

    def execute(self, grp_link):
        """Handle links in grp_link to corresponding Commands and executes them.

        Returns: None
        """
        for link in grp_link.links:
            cmd = self.commands[link.id]
            cmd.execute(link)


class Device:
    """A Device is the programming correspondence to a physical device. It may
    contain one or more OperationGroups. Device is the basic unit for configuration
    saving/loading and logging.
    """
    def __init__(self, name, desc=None):
        self.id = None
        self.name = name
        self.desc = desc
        self.groups = []

    def create_group(self, name, desc=None):
        """Create a new OperationGroup with name and desc.

        Returns: the create OperationGroup.
        """
        grp = OperationGroup(name, desc)
        grp_id = len(self.groups)
        grp.id = grp_id
        self.groups.append(grp)
        return grp

    def add_group(self, group):
        """Add an OperationGroup to this device and assign the group its id.

        Returns: assigned id
        """
        grp_id = len(self.groups)
        group.id = grp_id
        self.groups.append(group)
        return grp_id

    def get_link(self, node_link):
        """Get updates from groups, wrap them in a DeviceLink, then
        append them to node_link.

        Returns: the created link_pb2.DeviceLink
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id
        for grp in self.groups:
            grp.get_link(dev_link)
        return dev_link

    def get_full_link(self, node_link):
        """Get full updates from groups, wrap them in a DeviceLink, then
        append them to node_link.

        Returns: the created link_pb2.DeviceLink
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id
        for grp in self.groups:
            grp.get_full_link(dev_link)
        return dev_link

    def get_desc_link(self, dev_link):
        """Generate a description link to describe this Device, then
        append it to node_link.

        Returns: the created link_pb2.DeviceLink
        """
        dev_link = node_link.dev_links.add()
        dev_link.id = self.id
        dev_link.name = self.name
        dev_link.desc = self.desc
        for grp in self.groups:
            grp.get_desc_link(dev_link)
        return dev_link

    def execute(self, dev_link):
        """Handle links in dev_link to corresponding OperationGroups and executes them.

        Returns: None
        """
        for grp_link in dev_link.grp_links:
            grp = self.groups[grp_link.id]
            grp.execute(grp_link)

class Node:
    """A Node in smartlink corresponds to a network terminal, usually a computer,
     to control physical devices. A Node consists of one or multiple Devices.
    Node is the basic unit of network communication with control.
    """
    def __init__(self, name, desc=None):
        self.name = name
        self.desc = desc
        self.devices = []

    def add_device(self, device):
        """Add device to node and assign the device its id.

        Returns: the assigned id
        """
        dev_id = len(self.devices)
        device.dev_id = dev_id
        self.devices.append(device)
        return dev_id

    def add_devices(self, device_list):
        """Add a list of devices to node and assign them their id.

            Returns: None
            """
        for dev in device_list:
            self.add_device(dev)

    def get_link(self):
        """Get updates from devices and wrap them in a NodeLink.

        Returns: the created link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        for dev in self.devices:
            dev.get_link(node_link)
        return node_link

    def get_full_link(self):
        """Get full updates from devices and wrap them in a NodeLink.

        Returns: the created link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        for dev in self.devices:
            dev.get_full_link(node_link)
        return node_link

    def get_desc_link(self):
        """Generate a description link to describe this Node.

        Returns: the created link_pb2.NodeLink
        """
        node_link = link_pb2.NodeLink()
        node_link.name = self.name
        node_link.desc = self.desc
        for dev in self.devices:
            dev.get_desc_link(node_link)
        return node_link

    def execute(self, node_link):
        """Handle links in node_link to corresponding Devices and executes them.

        Returns: None
        """
        for dev_link in node_link.dev_links:
            dev = self.devices[dev_link.id]
            dev.execute(dev_link)


def start(reactor, factory, port):
    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])
    reactor.listenTCP(port, factory)
    reactor.run()
