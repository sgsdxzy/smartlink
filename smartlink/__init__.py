"""Common classes and routines."""
from collections.abc import Sequence

from smartlink import varint


class EndOfStreamError(EOFError):
    """Raised when the ther side closed connection."""
    pass


class ProtocalError(RuntimeError):
    """Raised when the other side of connection does not speak smartlink
    protocal."""
    pass


class StreamReadWriter:
    """Class for storing the StreaReader and StreamWriter pair"""
    __slots__ = ["_reader", "_writer"]

    def __init__(self, reader, writer):
        self._reader = reader
        self._writer = writer

    @property
    def peername(self):
        return self._writer.transport.get_extra_info('peername')

    async def read(self, n=-1):
        data = await self._reader.read(n)
        if data == b'':
            raise EndOfStreamError
        return data

    def write(self, data):
        self._writer.write(data)

    def write_bin_link(self, bin_link):
        """Write a varint representing the length of the serialized link, then
        write the link to writer.

        Returns: None.
        """
        self._writer.write(varint.encode(len(bin_link)))
        self._writer.write(bin_link)

    def close(self):
        self._writer.close()


def args_to_sequence(args):
    """Convert args to a sequence suitable for sending using smarlink."""
    if args is None:
        yield ''
        return
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
            elif isinstance(arg, bytearray):
                yield bytes(arg)
            elif arg == True:
                yield '1'
            elif arg == False:
                yield '0'
            else:
                yield str(arg)
        return
    yield str(args)
