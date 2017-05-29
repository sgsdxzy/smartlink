"""This module provides operation widgets for handling different argument types.
Widgets need to implement:
    get_arg() -> str
    set_arg(str)
These two methods shouldn't raise any exception.
"""
from PyQt5.QtWidgets import QLineEdit, QPushButton, QComboBox
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtCore import pyqtSlot


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
    """Widget for handling "str" type signature of update."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.setReadOnly(True)


class CStrWidget(StrWidget):
    """Widget for handling "str" type signature of command."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)


class UFloatWidget(UStrWidget):
    """Widget for handling "float" type signature of update."""

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


class UIntWidget(UStrWidget):
    """Widget for handling "int" type signature of update."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.validator = QIntValidator()
        self.setValidator(self.validator)


class CIntWidget(UStrWidget):
    """Widget for handling "int" type signature of command."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.validator = QIntValidator()
        self.setValidator(self.validator)


class UBoolWidget(QPushButton):
    """Widget for handling "bool" type argument of update."""
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


class CBoolWidget(QPushButton):
    """Widget for handling "bool" type argument of command."""
    _StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    _StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    _True_input = ("1", "T", "True", "Y", "t", "true")

    def __init__(self, ext_arg=None):
        super().__init__("OFF")
        self.setCheckable(True)
        self.setStyleSheet(self._StyleFalse)
        self.setMaximumWidth(32)
        self.toggled.connect(self._toggle)

    @pyqtSlot(bool)
    def _toggle(self, checked):
        if checked:
            self.setStyleSheet(self._StyleTrue)
            self.setText("ON")
            self.setChecked(True)
        else:
            self.setStyleSheet(self._StyleFalse)
            self.setText("OFF")
            self.setChecked(False)

    def set_arg(self, arg):
        if arg in self._True_input:
            self._toggle(True)
        else:
            self._toggle(False)

    def get_arg(self):
        if self.isChecked():
            return '1'
        else:
            return '0'


class UEnumWidget(UStrWidget):
    """Widget for handling "enum" type argument of update."""

    def __init__(self, ext_arg=None):
        super().__init__()
        self.setText("Unknown")
        self._items = ext_arg.split(';')

    def set_arg(self, arg):
        try:
            index = int(arg)
            self.setText(self._items[index])
        except (ValueError, IndexError):
            self.setText("Unknown")

    def get_arg(self):
        return self.text()

class CEnumWidget(QComboBox):
    """Widget for handling "enum" type argument of commands."""

    def __init__(self, ext_arg=None):
        super().__init__()
        self._items = ext_arg.split(';')
        self.addItems(self._items)

    def set_arg(self, arg):
        try:
            index = int(arg)
            self.setCurrentIndex(index)
        except (ValueError, IndexError):
            pass

    def get_arg(self):
        return str(self.currentIndex())
