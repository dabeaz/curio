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
    
async def main(host, port):
    while True:
        async with SignalSet(signal.SIGHUP) as sigset:
            print('Starting the server')
            serv_task = await new_task(run_server(host, port, echo_client))
            await sigset.wait()
            print('Server shutting down')
            await serv_task.cancel_children()
            await serv_task.cancel()

if __name__ == '__main__':
    kernel = Kernel(with_monitor=True)
    kernel.run(main('', 25000))
