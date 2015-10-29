# ssl_echo
#
# An example of a simple SSL echo server. 

import curio
from curio import ssl
from curio import network
import time

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

async def handle(client, addr):
    print('Connection from', addr)
    async with client:
        while True:
            data = await client.recv(1000)
            if not data:
                break
            await client.send(data)
    print('Connection closed')

if __name__ == '__main__':
    kernel = curio.Kernel()
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    kernel.run(network.run_server('', 10000, handle, ssl=ssl_context)
