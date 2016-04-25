# echoserv.py
#
# Echo server using streams

from curio import boot, run_server

async def echo_client(client, addr):
    print('Connection from', addr)
    reader, writer = client.make_streams()
    async with reader, writer:
        async for line in reader:
            await writer.write(line)
    print('Connection closed')

if __name__ == '__main__':
    boot(run_server('', 25000, echo_client))
