"""This module provides operation widgets for handling different argument types"""
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

class StrWidget(QLineEdit):
    """Widget for handling "str" type argument."""
    def __init__(self, ext_args=None):
        super().__init__()
        self.setMinimumWidth(40)
        if ext_args is not None:
            self.setText(ext_args)

    def exec_arg(self, arg):
        self.setText(arg)

    def get_arg(self):
        return self.text()


class CtrlStrWidget(StrWidget):
    """Widget for handling "str" type argument of control operation."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)
        self.setReadOnly(True)


class NodeStrWidget(StrWidget):
    """Widget for handling "str" type argument of node operation."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)


class CtrlFloatWidget(CtrlStrWidget):
    """Widget for handling "float" type argument of control operation."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)


class NodeFloatWidget(NodeStrWidget):
    """Widget for handling "float" type argument of node operation."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)
        if ext_args is None:
            self.setText("0")


class CtrlBoolWidget(QPushButton):
    """Widget for handling "bool" type argument."""
    StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    StyleDisabled = "QPushButton { color: #FFFFFF; background-color : #808080}"
    def __init__(self, ext_args=None):
        super().__init__("DIS")
        #self.state = None
        self.setStyleSheet(self.StyleDisabled)
        self.setMaximumWidth(32)

    def exec_arg(self, arg):
        if arg in ["1", "T", "True", "Y", "t", "true"]:
            self.setStyleSheet(self.StyleTrue)
            self.setText("ON")
            self.setChecked(True)
            #self.state = True
        else:
            self.setStyleSheet(self.StyleFalse)
            self.setText("OFF")
            self.setChecked(False)
            #self.state = False
