from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *

from smartlink import link_pb2

class NumExec:
    def __init__(self, op_id, dev_id, line_edit, button, node):
        self.op_id = op_id
        self.dev_id = dev_id
        self.le = line_edit
        self.btn = button
        self.node = node

    def slot_exec(self):
        node_link = link_pb2.NodeLink()
        dev_link = node_link.device_links.add()
        dev_link.device_id = self.dev_id
        link = dev_link.links.add()
        link.id = self.op_id
        link.args.append(self.le.text())

        str_link = node_link.SerializeToString()
        self.node.socket.write(str_link)
