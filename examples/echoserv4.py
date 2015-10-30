import signal
from curio import Kernel, new_task, SignalSet, CancelledError, run_server

async def echo_client(client, addr):
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

_tasks = set()

async def echo_manager(client, addr):
    child_task = await new_task(echo_client(client, addr))
    _tasks.add(child_task)
    try:
        await child_task.join()
    finally:
        _tasks.remove(child_task)
    
async def main(host, port):
    while True:
        async with SignalSet(signal.SIGHUP) as sigset:
            print('Starting the server')
            serv_task = await new_task(run_server(host, port, echo_manager))
            await sigset.wait()
            print('Server shutting down')
            await serv_task.cancel()
            for task in list(_tasks):
                await task.cancel()
            _tasks.clear()

if __name__ == '__main__':
    kernel = Kernel(with_monitor=True)
    kernel.run(main('', 25000))
