"""This module provides operation widgets for handling different argument types.
Widgets need to implement:
    get_arg() -> str
    set_arg(str)
These two methods shouldn't raise any exception.
"""
from PyQt5.QtWidgets import QLineEdit, QPushButton
from PyQt5.QtGui import QDoubleValidator

class StrWidget(QLineEdit):
    """Widget for handling "str" type signature."""

    def __init__(self, ext_arg=None):
        super().__init__()
        self.setMinimumWidth(40)
        if ext_arg is not None:
            self.setText(str(ext_arg))

    def get_arg(self):
        return self.text()

    def set_arg(self, arg):
        self.setText(str(arg))


class UStrWidget(StrWidget):
    """Widget for handling "str" type signature of update_from."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.setReadOnly(True)


class CStrWidget(StrWidget):
    """Widget for handling "str" type signature of command."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)


class UFloatWidget(UStrWidget):
    """Widget for handling "float" type signature of update_from."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)


class CFloatWidget(CStrWidget):
    """Widget for handling "float" type argument of command."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.validator = QDoubleValidator()
        self.setValidator(self.validator)


class UBoolWidget(QPushButton):
    """Widget for handling "bool" type argument of update_from."""
    _StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    _StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    _StyleUnknown = "QPushButton { color: #FFFFFF; background-color : #808080}"
    _True_input = ("1", "T", "True", "Y", "t", "true")
    _False_input = ("0", "F", "False", "N", "f", "false")

    def __init__(self, ext_arg=None):
        super().__init__("UKN")
        self.setStyleSheet(self._StyleUnknown)
        self.setMaximumWidth(32)

    def set_arg(self, arg):
        if arg in self._True_input:
            self.setStyleSheet(self._StyleTrue)
            self.setText("ON")
            self.setChecked(True)
        elif arg in self._False_input:
            self.setStyleSheet(self._StyleFalse)
            self.setText("OFF")
            self.setChecked(False)
        else:
            self.setStyleSheet(self._StyleUnknown)
            self.setText("UKN")
            self.setChecked(False)

    def get_arg(self):
        return self.text()
