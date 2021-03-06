import asyncio
from asyncio import ensure_future, IncompleteReadError
from concurrent.futures import CancelledError
import logging

from google.protobuf.message import DecodeError

from . import varint
from .common import StreamReadWriter, write_link, write_bin_link
from .link_pb2 import NodeLink

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
                            write_bin_link(client, bin_link)
                        # logs are successfully sent
                        self._node.clear_log()
                await asyncio.sleep(self._interval)
        except CancelledError:
            pass

    async def _create_client(self, reader, writer):
        try:
            client = StreamReadWriter(reader, writer)
            ip = client.get_extra_info('peername')
            logger.info("Accepted connection from {ip}.".format(ip=ip))

            # Send description link
            write_bin_link(client, self._str_desc)
            # wait for b'RDY' from client
            data = await client.readexactly(3)
            if data != b'RDY':
                # Not recognized respond
                logger.error(
                    "Response from client {ip} not recognized.".format(ip=ip))
                client.close()
                return

            self._clients.append(client)
            logger.info("Client from {ip} is ready.".format(ip=ip))

            # Send a full link
            write_link(client, self._node.get_full_update_link())

            # The work loop
            while True:
                length = await varint.decode(client)
                buf = await client.readexactly(length)
                cmd_link = NodeLink.FromString(buf)
                self._node.execute(cmd_link)
        except (IncompleteReadError, ConnectionError):
            # client disconnects
            logger.info("Client from {ip} disconnected.".format(ip=ip))
        except DecodeError:
            # purposely drop connection
            logger.error(
                "Failed to decode NodeLink from client {ip}".format(ip=ip))
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
