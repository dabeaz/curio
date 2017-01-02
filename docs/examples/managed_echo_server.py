import os
import signal
from curio import run, spawn, SignalSet, CancelledError, tcp_server, current_task

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
    finally:
        clients.remove(task)

async def main(host, port):
    while True:
        async with SignalSet(signal.SIGHUP) as sigset:
            print('Starting the server')
            serv_task = await spawn(tcp_server(host, port, echo_client))
            await sigset.wait()
            print('Server shutting down')
            await serv_task.cancel()

            for task in list(clients):
                await task.cancel()

if __name__ == '__main__':
    print('PID:', os.getpid())
    run(main('', 25000))
