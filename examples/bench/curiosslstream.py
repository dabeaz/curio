from curio import run, tcp_server
from curio import ssl
from socket import *


KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)


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
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
    run(tcp_server('', 25000, echo_handler, ssl=ssl_context))
