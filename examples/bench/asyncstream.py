# Example: A simple echo server written using asyncio streams

import asyncio

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
    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(echo_client, '127.0.0.1', 25000, loop=loop)
    loop.run_until_complete(coro)
    loop.run_forever()
