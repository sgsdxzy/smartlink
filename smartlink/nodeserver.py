import asyncio
from asyncio import ensure_future
from concurrent.futures import CancelledError
import logging

from smartlink import varint, EndOfStreamError, StreamReadWriter
from smartlink.link_pb2 import NodeLink
from google.protobuf.message import DecodeError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
sthandler = logging.StreamHandler()
fmt = logging.Formatter(datefmt='%Y-%m-%d %H:%M:%S',
                        fmt="[SERVER:{levelname}]\t{asctime}\t{message}", style='{')
sthandler.setFormatter(fmt)
logger.addHandler(sthandler)


class NodeServer:
    """Asyncio socket server for handling connection from controls."""

    def __init__(self, node, interval=0.2, loop=None):
        """node is a smartlink.Node object.
        interval is the time interval between checking updates.
        loop is an asyncio event loop.
        """
        if loop is None:
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
        logger.info(
            "Starting server at port {port}...".format(port=port))
        self._server = self._loop.run_until_complete(
            asyncio.start_server(self._create_client, host, port, loop=self._loop))
        self._announce_task = ensure_future(self._announce())
        self._running = True
        logger.info("Server started.")

    def close(self):
        assert self._running, "Server is not running!"
        logger.info("Stopping server...")
        self._announce_task.cancel()
        self._announce_task = None
        self._clients.clear()
        self._server.close()
        self._loop.run_until_complete(self._server.wait_closed())
        self._node.close()
        self._running = False
        logger.info("Server stopped.")

    async def _announce(self):
        try:
            while True:
                if self._clients:
                    update_link = self._node.get_update_link()
                    bin_link = update_link.SerializeToString()
                    if bin_link:
                        # Write only when there's news to write
                        for client in self._clients:
                            client.write_bin_link(bin_link)
                        # logs are successfully sent
                        self._node.clear_log()
                await asyncio.sleep(self._interval)
        except CancelledError:
            pass

    async def _create_client(self, reader, writer):
        try:
            client = StreamReadWriter(reader, writer)
            logger.info("Accepted connection from {ip}.".format(
                ip=client.peername))

            # Send description link
            client.write_bin_link(self._str_desc)
            # wait for b'RDY' from client
            data = await client.read(3)
            while len(data) < 3:
                data += await client.read(3 - len(data))
            if data != b'RDY':
                # Not recognized respond
                logger.error(
                    "Response from client {ip} not recognized.".format(ip=client.peername))
                client.close()
                return

            self._clients.append(client)
            logger.info("Client from {ip} is ready.".format(
                ip=client.peername))

            # Send a full link
            full_link = self._node.get_full_update_link()
            bin_link = full_link.SerializeToString()
            client.write_bin_link(bin_link)

            # The work loop
            while True:
                length = await varint.decode(client)
                buf = await client.read(length)
                while len(buf) < length:
                    buf += await client.read(length - len(buf))
                cmd_link = NodeLink.FromString(buf)
                self._node.execute(cmd_link)
        except (EndOfStreamError, ConnectionError):
            # client disconnects
            logger.info("Client from {ip} disconnected.".format(
                ip=client.peername))
        except DecodeError:
            # purposely drop connection
            logger.error(
                "Failed to decode NodeLink from client {ip}".format(ip=client.peername))
        except Exception:
            logger.exception("Unexpected Error!")
        finally:
            # cleanups
            client.close()
            try:
                self._clients.remove(client)
            except ValueError:
                # Client lost connection before it is ready
                pass
