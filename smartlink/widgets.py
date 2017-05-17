"""This module provides operation widgets for handling different argument types"""
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

class QHLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)

class QVLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Sunken)

class StrWidget(QLineEdit):
    """Widget for handling "str" type signature."""
    def __init__(self, ext_args=None):
        super().__init__()
        self.setMinimumWidth(40)
        if ext_args is not None:
            self.setText(ext_args)

    def update(self, arg):
        self.setText(arg)

    def get_cmd(self):
        return self.text()


class UStrWidget(StrWidget):
    """Widget for handling "str" type signature of update."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)
        self.setReadOnly(True)


class CStrWidget(StrWidget):
    """Widget for handling "str" type signature of command."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)


class UFloatWidget(UStrWidget):
    """Widget for handling "float" type signature of update."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)


class CFloatWidget(CStrWidget):
    """Widget for handling "float" type argument of command."""
    def __init__(self, ext_args=None):
        super().__init__(ext_args)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)


class UBoolWidget(QPushButton):
    """Widget for handling "bool" type argument of update."""
    StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    StyleUnknown = "QPushButton { color: #FFFFFF; background-color : #808080}"
    True_input = ("1", "T", "True", "Y", "t", "true")
    False_input = ("0", "F", "False", "N", "f", "false")
    def __init__(self, ext_args=None):
        super().__init__("UKN")
        #self.state = None
        self.setStyleSheet(self.StyleUnknown)
        self.setMaximumWidth(32)

    def update(self, arg):
        if arg in self.True_input:
            self.setStyleSheet(self.StyleTrue)
            self.setText("ON")
            self.setChecked(True)
        elif arg in self.False_input:
            self.setStyleSheet(self.StyleFalse)
            self.setText("OFF")
            self.setChecked(False)
        else:
            self.setStyleSheet(self.StyleUnknown)
            self.setText("UKN")
            self.setChecked(False)
