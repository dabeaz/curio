# ssl_echo
#
# An example of a simple SSL server.  To test, connect via browser

import curio
from curio import ssl
import time

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

async def handler(client, addr):
    reader, writer = client.make_streams()
    async for line in reader:
        line = line.strip()
        if not line:
            break
        print(line)

    await writer.write(
b'''HTTP/1.0 200 OK\r
Content-type: text/plain\r
\r
If you're seeing this, it probably worked. Yay!
''')
    await writer.write(time.asctime().encode('ascii'))
    await writer.close()
    await reader.close()

if __name__ == '__main__':
    kernel = curio.Kernel()
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    kernel.run(curio.run_server('', 10000, handler, ssl=ssl_context))
