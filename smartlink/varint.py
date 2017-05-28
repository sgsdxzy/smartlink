"""Varint encoder/decoder

varints are a common encoding for variable length integer data, used in
libraries such as sqlite, protobuf, v8, and more.

This module adapts from https://github.com/fmoo/python-varint/blob/master/varint.py,
but instead of working on stream, it works on asyncio.ReaderStream.
"""


def encode(number):
    """Pack `number` into varint bytes"""
    buf = bytearray()
    while True:
        towrite = number & 0x7f
        number >>= 7
        if number:
            buf.append(towrite | 0x80)
        else:
            buf.append(towrite)
            break
    return buf


async def decode(stream):
    """Read a varint from `stream`"""
    shift = 0
    result = 0
    while True:
        i = ord(await stream.read(1))
        result |= (i & 0x7f) << shift
        shift += 7
        if not (i & 0x80):
            break
    return result
