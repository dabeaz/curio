# curiosslecho.py
#
# Use sslclient.py to test

import curio
from curio import ssl
from curio import network
from socket import *

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

async def handle(client, addr):
    print('Connection from', addr)
    client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    async with client:
        while True:
            data = await client.recv(100000)
            if not data:
                break
            await client.sendall(data)
    print('Connection closed')

if __name__ == '__main__':
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    curio.run(network.tcp_server('', 25000, handle, ssl=ssl_context))
