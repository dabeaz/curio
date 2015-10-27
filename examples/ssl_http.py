# ssl_echo
#
# An example of a simple SSL server.  To test, connect via browser

import curio
from curio import socket
from curio import ssl

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

async def handle(client):
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
    print('Connection closed')
    await client_f.close()
    client.close()

async def run_server(address):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
    s.bind(address)
    s.listen(1)
    
    # Wrap with an SSL layer
    s_ssl = ssl.wrap_socket(s, keyfile=KEYFILE, certfile=CERTFILE, server_side=True, ssl_version=ssl.PROTOCOL_SSLv23)

    print("Listening for connections on", address)
    # Wait for connections
    while True:
        try:
            c,a = await s_ssl.accept()
            print("Got connection", c, a)
            await curio.new_task(handle(c))
        except Exception as e:
            print("%s: %s" % (e.__class__.__name__, e))

if __name__ == '__main__':
    kernel = curio.Kernel()
    kernel.add_task(run_server(('',10000)))
    kernel.run()
