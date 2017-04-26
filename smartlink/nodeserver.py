from twisted.internet import protocol, task
from twisted.logger import globalLogBeginner, textFileLogObserver
from sys import stdout

import smartlink.smartlink_pb2 as pb2

class SmartlinkControl(protocol.Protocol):
    def connectionMade(self):
        self.factory.clientConnectionMade(self)
        self.clientReady = False
    def connectionLost(self, reason):
        self.factory.clientConnectionLost(self)

    def dataReceived(self, data):
        if not self.clientReady:
            try:
                if data.decode("utf-8") == "READY":
                    self.clientReady = True
                    self.factory.clientReady(self)
            except:
                pass
            return
        try:
            operation = pb2.DeviceOperation.FromString(data)
            self.factory.operationHandler[operation.devicename][operation.operation](operation.args)
        except:
            if self.factory.logger:
                self.factory.logger.warn("{prefix} failed to execute operation from {peer}".\
                format(prefix = self.logPrefix(), peer=self.transport.getPeer()))
            raise

class SmartlinkFactory(protocol.Factory):
    protocol = SmartlinkControl
    def __init__(self, frequency = 1, logger = None, operationHandler = None, updateHandler = None, nodeDescription = None):
        self.broadcast = []
        self.operationHandler = operationHandler
        self.updateHandler = updateHandler
        self.nodeDescription = nodeDescription
        if self.nodeDescription :
            self.strDescription = nodeDescription.SerializeToString()
        self.lc = task.LoopingCall(self.announce)
        self.lc.start(1/frequency)
        self.logger = logger

    def announce(self):
        nodeUpdate = pb2.NodeUpdate()
        for deviceName, getStatusFuncList in self.updateHandler.items():
            deviceUpdate = nodeUpdate.updates.add()
            deviceUpdate.name = deviceName
            for getStatusFunc in getStatusFuncList:
                deviceUpdate.status.append(getStatusFunc())
        strData = nodeUpdate.SerializeToString()
        for client in self.broadcast:
            client.transport.write(strData)

    def clientConnectionMade(self, client):
        if self.strDescription :
            client.transport.write(self.strDescription)

    def clientReady(self, client):
        self.broadcast.append(client)

    def clientConnectionLost(self, client):
        try:
            self.broadcast.remove(client)
        except ValueError:
            pass

class Node:
    """Helper class for generating DeviceHandler, Updatehandler and NodeDescription for SmartlinkFactory"""
    def __init__(self, name, description):
        self.operationHandler = {}
        self.updateHandler = {}
        self.nodeDescription = pb2.NodeDescription()
        self.nodeDescription.name = name
        self.nodeDescription.description = description

    def addDevice(self, name, description, operationList, updateList):
        """name: name of device
           description: description of device
           operationList: a list of (operationName, operationFunction, operationArgs...)
           updateList: a list of updateFunction
           """
        self.updateHandler[name] = updateList

        deviceDescription = self.nodeDescription.devices.add()
        deviceDescription.name = name
        deviceDescription.description = description

        operationDict = {}
        for operation in operationList:
            operationDict[operation[0]] = operation[1]

            opDescription = deviceDescription.operations.add()
            opDescription.name = operation[0]
            #if len(operation) > 2:
            opDescription.args.extend(operation[2:])
        self.operationHandler[name] = operationDict


def start(reactor, factory, port):
    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])
    reactor.listenTCP(port, factory)
    reactor.run()
