# Example: A simple echo server written using a file-like object

from curio import Kernel, new_task
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
             await new_task(echo_client(client))

async def echo_client(client):
    async with client.makefile('rwb') as client_f:
         async for line in client_f:
             await client_f.write(line)
    await client.close()
    print('Connection closed')

if __name__ == '__main__':
     kernel = Kernel()
     kernel.add_task(echo_server(('',25000)))
     kernel.run()
