# A simple echo server written using the socketserver API with streams

from curio import Kernel, new_task
from curio.socketserver import *

class EchoHandler(StreamRequestHandler):
    async def handle(self):
        print('Connection from', self.client_address)
        async for line in self.rfile:
            await self.wfile.write(line)

        print('Connection closed')

if __name__ == '__main__':
    serv = TCPServer(('',25000), EchoHandler)
    kernel = Kernel()
    kernel.add_task(serv.serve_forever())
    kernel.run()
