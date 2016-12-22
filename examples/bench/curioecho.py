# A simple echo server

from curio import run, tcp_server
from curio.socket import IPPROTO_TCP, TCP_NODELAY

async def echo_handler(client, addr):
    print('Connection from', addr)
    client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    while True:
        data = await client.recv(1000000)
        if not data:
            break
        await client.sendall(data)
    print('Connection closed')

if __name__ == '__main__':
    run(tcp_server('', 25000, echo_handler))
