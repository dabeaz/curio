# Example: A simple echo server written directly with sockets

from curio import Kernel, spawn
from curio.socket import *

async def echo_server(address):
    sock = socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    print('Server listening at', address)
    async with sock:
        while True:
             client, addr = await sock.accept()
             print('Connection from', addr)
             await spawn(echo_client(client))

async def echo_client(client):
    async with client:
         while True:
             data = await client.recv(10000)
             if not data:
                  break
             await client.sendall(data)
    print('Connection closed')

if __name__ == '__main__':
     kernel = Kernel()
     kernel.run(echo_server(('',25000)))
