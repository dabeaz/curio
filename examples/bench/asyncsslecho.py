# Example: A simple echo server written using asyncio streams

import asyncio
import ssl

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

async def echo_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print('Connection from', addr)
    while True:
        data = await reader.read(100000)
        if not data:
            break
        writer.write(data)
        await writer.drain()
    print('Connection closed')

if __name__ == '__main__':
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)

    # import uvloop
    # asyncio.set_event_loop(uvloop.new_event_loop())

    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(echo_client, '127.0.0.1', 25000, loop=loop, ssl=context)
    loop.run_until_complete(coro)
    loop.run_forever()
