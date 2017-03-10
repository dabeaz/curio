# Echo server with cancellation and signal handling

import signal
from curio import (run, spawn, SignalEvent, CancelledError, tcp_server,
                   current_task)

clients = set()


async def echo_client(client, addr):
    task = await current_task()
    clients.add(task)
    print('Connection from', addr)
    try:
        while True:
            data = await client.recv(1000)
            if not data:
                break
            await client.sendall(data)
        print('Connection closed')
    except CancelledError:
        await client.sendall(b'Server going down\n')
        raise
    finally:
        clients.remove(task)


async def main(host, port):
    while True:
        goodbye = SignalEvent(signal.SIGHUP)
        print('Starting the server')
        serv_task = await spawn(tcp_server, host, port, echo_client)
        await goodbye.wait()
        print('Server shutting down')
        await serv_task.cancel()

        for task in list(clients):
            await task.cancel()


if __name__ == '__main__':
    try:
        run(main, '', 25000)
    except KeyboardInterrupt:
        pass
