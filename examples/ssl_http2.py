# ssl_echo
#
# An example of a simple SSL server.  To test, connect via browser

import curio
from curio import socket
from curio import ssl
from curio import network
import time

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

async def handle(client, addr):
    client_f = client.makefile('rwb')
    async for line in client_f:
        line = line.strip()
        if not line:
            break
        print(line)

    await client_f.write(
b'''HTTP/1.0 200 OK\r
Content-type: text/plain\r
\r
If you're seeing this, it probably worked. Yay!
''')
    await client_f.write(time.asctime().encode('ascii'))

    print('Connection closed')
    await client_f.close()
    await client.close()

if __name__ == '__main__':
    kernel = curio.Kernel()
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    kernel.run(network.start_tcp_server('', 10000, handle, ssl=ssl_context))
