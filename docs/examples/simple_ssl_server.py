import curio
from curio import ssl
import time

KEYFILE = 'privkey_rsa'       # Private key
CERTFILE = 'certificate.crt'  # Server certificate

async def handler(client, addr):
    client_f = client.as_stream()

    # Read the HTTP request
    async for line in client_f:
        line = line.strip()
        if not line:
            break
        print(line)

    # Send a response
    await client_f.write(
        b'''HTTP/1.0 200 OK\r
        Content-type: text/plain\r
        \r
        If you're seeing this, it probably worked. Yay!
        ''')
    await client_f.write(time.asctime().encode('ascii'))
    await client.close()

if __name__ == '__main__':
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    curio.run(curio.tcp_server('', 10000, handler, ssl=ssl_context))
