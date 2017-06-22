"""Common classes and routines."""
from collections.abc import Sequence

from smartlink import varint
from smartlink.node import Device, Node
from smartlink.nodeserver import NodeServer
from smartlink.qtpanel import NodePanel


class StreamReadWriter:
    """Class for storing the StreaReader and StreamWriter pair"""
    __slots__ = ["reader", "writer"]

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    async def read(self, n=-1):
        return await self.reader.read(n)

    async def readline(self):
        return await self.reader.readline()

    async def readexactly(self, n):
        return await self.reader.readexactly(n)

    async def readuntil(self, separator=b'\n'):
        return await self.reader.readuntil(separator)

    def at_eof(self):
        return self.reader.at_eof()

    def can_write_eof(self):
        return self.writer.can_write_eof()

    def close(self):
        self.writer.close()

    async def drain(self):
        await self.writer.drain()

    def get_extra_info(self, name, default=None):
        return self.writer.get_extra_info(name, default)

    def write(self, data):
        self.writer.write(data)

    def writelines(self, data):
        self.writer.writelines(data)

    def write_eof(self):
        self.writer.write_eof()


def write_link(writer, link):
    """Serialize the link, Write a varint representing the length
    of the serialized link, then write the link to writer.

    Returns: None.
    """
    bin_link = link.SerializeToString()
    writer.write(varint.encode(len(bin_link)))
    writer.write(bin_link)


def write_bin_link(writer, bin_link):
    """Write a varint representing the length of the serialized link, then
    write the link to writer.

    Returns: None.
    """
    writer.write(varint.encode(len(bin_link)))
    writer.write(bin_link)


def args_to_sequence(args):
    """Convert args to a sequence suitable for sending using smarlink."""
    if isinstance(args, str) or isinstance(args, bytes):
        yield args
        return
    if isinstance(args, bytearray):
        yield bytes(args)
        return
    if isinstance(args, Sequence):
        for arg in args:
            if arg is None:
                yield ''
            elif isinstance(arg, bytes):
                yield arg
            elif isinstance(arg, bytearray):
                yield bytes(arg)
            elif arg is True:
                yield '1'
            elif arg is False:
                yield '0'
            else:
                yield str(arg)
        return
    if args is True:
        yield '1'
        return
    if args is False:
        yield '0'
        return
    if args is None:
        return
    yield str(args)
