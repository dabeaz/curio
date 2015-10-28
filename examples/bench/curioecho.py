# A simple echo server written using the socketserver API

from curio import Kernel, new_task
from curio.socketserver import *

class EchoHandler(BaseRequestHandler):
    async def handle(self):
        print('Connection from', self.client_address)
        while True:
            data = await self.request.recv(10000)
            if not data:
                break
            await self.request.send(data)
        print('Connection closed')

if __name__ == '__main__':
    serv = TCPServer(('',25000), EchoHandler)
    kernel = Kernel()
    kernel.run(serv.serve_forever())
