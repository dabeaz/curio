# Example: A simple echo server written using streams

from curio import run, spawn
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
    s = client.as_stream()
    async for line in s:
        await s.write(line)
    await client.close()
    print('Connection closed')

if __name__ == '__main__':
    try:
        run(echo_server(('', 25000)))
    except KeyboardInterrupt:
        pass
