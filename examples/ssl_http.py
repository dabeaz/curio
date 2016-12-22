# ssl_http
#
# An example of a simple SSL server.  To test, connect via browser

import os
import curio
from curio import ssl
import time


KEYFILE = os.path.dirname(__file__) + "/ssl_test_rsa"    # Private key
# Certificate (self-signed)
CERTFILE = os.path.dirname(__file__) + "/ssl_test.crt"


async def handler(client, addr):
    s = client.as_stream()
    async for line in s:
        line = line.strip()
        if not line:
            break
        print(line)

    await s.write(
        b'''HTTP/1.0 200 OK\r
Content-type: text/plain\r
\r
If you're seeing this, it probably worked. Yay!
''')
    await s.write(time.asctime().encode('ascii'))
    await client.close()


if __name__ == '__main__':
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    print('Connect to https://localhost:10000 to see if it works')
    try:
        curio.run(curio.tcp_server('', 10000, handler, ssl=ssl_context))
    except KeyboardInterrupt:
        pass
