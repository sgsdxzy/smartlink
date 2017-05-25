import asyncio
from asyncio import ensure_future
from concurrent.futures import CancelledError, TimeoutError
import logging

from smartlink import varint, EndOfStreamError, ProtocalError, StreamReadWriter
from smartlink.link_pb2 import NodeLink
from google.protobuf.message import DecodeError

class NodeServer:
    """Asyncio socket server for handling connection from controls."""
    def __init__(self, node, interval=0.5, loop=None):
        """node is a smartlink.Node object.
        interval is the time interval between checking updates.
        loop is an asyncio event loop.
        """
        if loop == None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._node = node
        desc_link = node.get_desc_link()
        self._str_desc = desc_link.SerializeToString()
        self._interval = interval
        self._clients = []
        self._server = None
        self._running = False
        self._announce_task = None

    def start(self, host=None, port=5362):
        assert not self._running, "Server is already running!"
        logging.info("Starting server listening at port {port}...".format(port=port))
        self._server = self._loop.run_until_complete(\
            asyncio.start_server(self._create_client, host, port, loop=self._loop))
        self._announce_task = ensure_future(self._announce())
        self._running = True
        logging.info("Server started.")

    def close(self):
        assert self._running, "Server is not running!"
        logging.info("Stopping server...")
        self._announce_task.cancel()
        self._announce_task = None
        self._clients.clear()
        self._server.close()
        self._loop.run_until_complete(self._server.wait_closed())
        self._running = False
        logging.info("Server stopped.")

    async def _announce(self):
        try:
            while True:
                update_link = self._node.get_link()
                bin_link = update_link.SerializeToString()
                if bin_link:
                    #Write only when there's news to write
                    for client in self._clients:
                        client.write_bin_link(bin_link)
                await asyncio.sleep(self._interval)
        except CancelledError:
            pass

    async def _create_client(self, reader, writer):
        client = StreamReadWriter(reader, writer)
        logging.info("Accepted connection from {ip}.".format(ip=client.peername))
        try:
            #Send description link
            client.write_bin_link(self._str_desc)

            #wait for b'RDY' from client
            data = await client.read(3)
            while len(data) < 3:
                data+= await client.read(3-len(data))
            if data != b'RDY':
                #Not recognized respond
                raise ProtocalError
            self._clients.append(client)
            logging.info("Client from {ip} is ready.".format(ip=client.peername))

            #Send a full link
            full_link = self._node.get_full_link()
            bin_link = full_link.SerializeToString()
            client.write_bin_link(bin_link)

            #The work loop
            while True:
                #Parse NodeLink
                length = await varint.decode(client)
                buf = await client.read(length)
                while len(buf) < length:
                    buf += await client.read(length-len(buf))
                cmd_link = NodeLink.FromString(buf)

                self._node.execute(cmd_link)
        except EndOfStreamError:
            #client disconnects
            logging.info("Client from {ip} disconnected.".format(ip=client.peername))
            pass
        except (ProtocalError, DecodeError):
            #purposely drop connection
            logging.warning("Dropping misbehaving client at {ip}".format(ip=client.peername))
            client.close()
        finally:
            #cleanups
            try:
                self._clients.remove(client)
            except ValueError:
                # Client lost connection before it is ready
                pass
