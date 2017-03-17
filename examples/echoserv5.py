import signal
from curio import run, spawn, SignalQueue, CancelledError, tcp_server
from curio.socket import *

async def echo_client(client, addr):
    print('Connection from', addr)
    s = client.as_stream()
    try:
        async for line in s:
            await s.write(line)
    except CancelledError:
        await s.write(b'SERVER IS GOING DOWN!\n')
        raise
    print('Connection closed')

async def main(host, port):
    async with SignalQueue(signal.SIGHUP) as restart:
        while True:
            print('Starting the server')
            serv_task = await spawn(tcp_server, host, port, echo_client)
            await restart.get()
            print('Server shutting down')
            await serv_task.cancel()

if __name__ == '__main__':
    run(main('', 25000))
