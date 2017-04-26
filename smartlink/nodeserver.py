from twisted.internet import protocol, task
from twisted.logger import globalLogBeginner, textFileLogObserver
from sys import stdout

import smartlink.smartlink_pb2 as pb2

class SmartlinkControl(protocol.Protocol):
    def connectionMade(self):
        self.factory.clientConnectionMade(self)
    def connectionLost(self, reason):
        self.factory.clientConnectionLost(self)

    def dataReceived(self, data):
        try:
            op = pb2.DeviceOperation.FromString(data)
            self.factory.DeviceHandler[op.devicename][op.operation](op.args)
        except:
            if self.factory.logger:
                self.factory.logger.warn("{prefix} failed to execute operation from {peer}".format(prefix = self.logPrefix(), peer=self.transport.getPeer()))
            #raise

class SmartlinkFactory(protocol.Factory):
    protocol = SmartlinkControl
    def __init__(self, frequency = 1, logger = None, DeviceHandler = None, UpdateHandler = None, NodeDescription = None):
        self.clients = []
        self.DeviceHandler =DeviceHandler
        self.UpdateHandler = UpdateHandler
        self.NodeDescription = NodeDescription
        self.lc = task.LoopingCall(self.announce)
        self.lc.start(1/frequency)
        self.logger = logger

    def announce(self):
        for client in self.clients:
            client.transport.write("Posiiton is {0}\n".format(self.UpdateHandler()).encode('utf-8'))

    def clientConnectionMade(self, client):
        self.clients.append(client)

    def clientConnectionLost(self, client):
        self.clients.remove(client)

def start(reactor, factory, port):
    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])
    reactor.listenTCP(port, factory)
    reactor.run()
