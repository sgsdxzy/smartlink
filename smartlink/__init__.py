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
