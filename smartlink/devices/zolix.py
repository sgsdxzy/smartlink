import serial

class SC300:
    """Class for Zolix SC300 controller. All operations are async."""
    X = b'X'
    Y = b'Y'
    Z = b'Z'

    def __init__(self):
        self.buffer = bytearray()
        self.parsers = []
        self.ser = serial.Serial()
        self.ser.baudrate = 19200
        self.ser.timeout = 0
        self.ser.write_timeout = 0

    def open(self, port):
        self.ser.port = port
        self.ser.open()

        self.ser.write(b'VE\r')
        self.parser.append(self.verify)
        self.try_parse()

    def close(self):
        if self.ser.is_open():
            self.ser.close()

    def 

    def try_parse(self):
        self.buffer.extend(self.ser.read(1024))
        sep = self.buffer.find(b'\r)
        while sep != -1:
            parser = self.parsers.pop(0)
            if parser is not None:
                parser(self.buffer[:sep])
            self.buffer = self.buffer[sep+1:]
            sep = self.buffer.find(b'\r)

    def ask_position(self, axis):
        self.ser.write(b'?%c\r' % axis)

    def zero(self, axis):
        self.ser.write(b'H%c\r' % axis)

    def relative_move(self, axis, n):
        if n>0:
            self.ser.write(b'+%c,%d' % n)

    def read(self):
        answer = self.ser.read(1024)
        print(answer)
