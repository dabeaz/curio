from curio import run, spawn, tcp_server
from socket import *


async def echo_handler(client, addr):
    print('Connection from', addr)
    try:
        client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    except (OSError, NameError):
        pass
    s = client.as_stream()
    while True:
        data = await s.read(102400)
        if not data:
            break
        await s.write(data)
    await s.close()
    print('Connection closed')


if __name__ == '__main__':
    run(tcp_server, '', 25000, echo_handler)
