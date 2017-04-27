from twisted.internet import protocol, task
from twisted.logger import globalLogBeginner, textFileLogObserver
from sys import stdout

from smartlink import link_pb2

class SmartlinkControl(protocol.Protocol):
    def connectionMade(self):
        self.factory.clientConnectionMade(self)
        self.clientReady = False
    def connectionLost(self, reason):
        self.factory.clientConnectionLost(self)

    def dataReceived(self, data):
        if not self.clientReady:
            try:
                if data.decode("utf-8") == "RDY":
                    self.clientReady = True
                    self.factory.clientReady(self)
            except:
                pass
            return
        try:
            nodeOpLink = link_pb2.NodeLink.FromString(data)
            for devOpLink in nodeOpLink.devLink:
                devOpHandler = self.factory.nodeOpHandler[devOpLink.devName]
                for opLink in devOpLink.link:
                    devOpHandler[opLink.name](opLink.args)
        except:
            if self.factory.logger:
                self.factory.logger.warn("{prefix} failed to execute operation from {peer}".\
                format(prefix = self.logPrefix(), peer=self.transport.getPeer()))
            raise

class SmartlinkFactory(protocol.Factory):
    protocol = SmartlinkControl
    def __init__(self, frequency = 1, logger = None, ctrlOpHandler = None, nodeOpHandler = None, nodeDesc = None,):
        self.broadcast = []
        self.ctrlOpHandler = ctrlOpHandler
        self.nodeOpHandler = nodeOpHandler
        self.nodeDesc = nodeDesc
        if self.nodeDesc:
            self.strNodeDesc = nodeDesc.SerializeToString()
        self.lc = task.LoopingCall(self.announce)
        self.lc.start(1/frequency)
        self.logger = logger

    def announce(self):
        ctrlOpLink = link_pb2.NodeLink()
        for devName, ctrlOpList in self.ctrlOpHandler.items():
            devOpLink = ctrlOpLink.devLink.add()
            devOpLink.devName = devName
            for opName, opFunc in ctrlOpList:
                opLink = devOpLink.link.add()
                opLink.name = opName
                opLink.args.extend(opFunc())
        strData = ctrlOpLink.SerializeToString()
        #print(len(strData))
        for client in self.broadcast:
            client.transport.write(strData)

    def clientConnectionMade(self, client):
        if self.strNodeDesc :
            client.transport.write(self.strNodeDesc)

    def clientReady(self, client):
        self.broadcast.append(client)

    def clientConnectionLost(self, client):
        try:
            self.broadcast.remove(client)
        except ValueError:
            pass


class Node:
    """Helper class for generating nodeOpHandler, ctrlOpHandler and nodeDesc for SmartlinkFactory"""
    def __init__(self, name, description):
        self.nodeOpHandler = {}
        self.ctrlOpHandler = {}

        self.nodeDesc = link_pb2.NodeLink()
        self.nodeDesc.nodeName = name
        self.nodeDesc.nodeDesc = description
        self.nodeDesc.type = link_pb2.NodeLink.DESCRIPTION

    def addDevice(self, name, description, ctrlOpList = None, nodeOpList = None):
        """Add device to node
           name: name of device
           description: description of device
           ctrlOpList: the list of operations called by node to execute on control, list of (opName, opFunc)
           nodeOpList: the list of operations called by control to execute on node, list of (opName, opFunc, opArgs...)
           """
        self.ctrlOpHandler[name] = ctrlOpList

        devDescLink = self.nodeDesc.devLink.add()
        devDescLink.devName = name
        devDescLink.devDesc = description
        for op in ctrlOpList:
            opDescLink = devDescLink.link.add()
            opDescLink.name = op[0]

        nodeDevOpDict = {}
        for op in nodeOpList:
            nodeDevOpDict[op[0]] = op[1]
            opDescLink = devDescLink.link.add()
            opDescLink.name = op[0]
            opDescLink.args.extend(op[2:])
        self.nodeOpHandler[name] = nodeDevOpDict


def start(reactor, factory, port):
    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])
    reactor.listenTCP(port, factory)
    reactor.run()
