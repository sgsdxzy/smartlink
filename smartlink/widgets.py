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
        self.setMinimumWidth(30)
        if ext_arg is not None:
            self.setText(ext_arg)

    def get_arg(self):
        return self.text()

    def set_arg(self, arg):
        self.setText(arg)
        self.updateGeometry()


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


class CIntWidget(CStrWidget):
    """Widget for handling "int" type signature of command."""

    def __init__(self, ext_arg=None):
        super().__init__(ext_arg)
        self.validator = QIntValidator()
        self.setValidator(self.validator)


class UBoolWidget(QPushButton):
    """Widget for handling "bool" type argument of update."""
    StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    StyleUnknown = "QPushButton { color: #FFFFFF; background-color : #808080}"

    def __init__(self, ext_arg=None):
        super().__init__("UKN")
        self.setStyleSheet(self.StyleUnknown)
        self.setMaximumWidth(32)

    def set_arg(self, arg):
        if arg == '1':
            self.setStyleSheet(self.StyleTrue)
            self.setText("ON")
            self.setChecked(True)
        elif arg == '0':
            self.setStyleSheet(self.StyleFalse)
            self.setText("OFF")
            self.setChecked(False)
        else:
            self.setStyleSheet(self.StyleUnknown)
            self.setText("UKN")
            self.setChecked(False)

    def get_arg(self):
        return self.text()


class CBoolWidget(QPushButton):
    """Widget for handling "bool" type argument of command."""
    StyleTrue = "QPushButton { color: #000000; background-color : #00FF00}"
    StyleFalse = "QPushButton { color: #FFFFFF; background-color : #FF0000}"
    _True_input = ("1", "T", "True", "Y", "t", "true")

    def __init__(self, ext_arg=None):
        super().__init__("OFF")
        self.setCheckable(True)
        self.setStyleSheet(self.StyleFalse)
        self.setMaximumWidth(32)
        self.toggled.connect(self._toggle)

    @pyqtSlot(bool)
    def _toggle(self, checked):
        if checked:
            self.setStyleSheet(self.StyleTrue)
            self.setText("ON")
            self.setChecked(True)
        else:
            self.setStyleSheet(self.StyleFalse)
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
            self.updateGeometry()
        except (ValueError, IndexError):
            self.setText("Unknown")
            self.updateGeometry()

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
