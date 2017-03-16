import signal
from curio import run, spawn, SignalEvent, CancelledError, TaskGroup
from curio.socket import *

async def echo_client(client, addr):
    print('Connection from', addr)
    async with client:
        try:
            while True:
                data = await client.recv(1000)
                if not data:
                    break
                await client.sendall(data)
            print('Connection closed')
        except CancelledError:
            await client.sendall(b'Server going away\n')
            raise

async def tcp_server(address, handler):
    async with TaskGroup() as clients:
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(1)
        async with sock:
            while True:
                client_sock, addr = await sock.accept()
                await clients.spawn(handler, client_sock, addr, daemon=True)

async def main(host, port):
    restart = SignalEvent(signal.SIGHUP)
    while True:
        print('Starting the server')
        serv_task = await spawn(tcp_server, (host, port), echo_client)
        await restart.wait()
        restart.clear()
        print('Server shutting down')
        await serv_task.cancel()

if __name__ == '__main__':
    run(main('', 25000))
