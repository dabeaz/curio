import asyncio
from socket import *


class EchoProtocol(asyncio.Protocol):

    def connection_made(self, transport):
        self.transport = transport
        sock = transport.get_extra_info('socket')
        try:
            sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
        except (OSError, NameError):
            pass

    def connection_lost(self, exc):
        self.transport = None

    def data_received(self, data):
        self.transport.write(data)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    coro = loop.create_server(EchoProtocol, '', 25000)
    srv = loop.run_until_complete(coro)
    loop.run_forever()
