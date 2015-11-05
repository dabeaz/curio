# A simple echo server 

from curio import Kernel, new_task, run_server


async def echo_handler(client, addr):
    print('Connection from', addr)
    while True:
        data = await client.recv(10000)
        if not data:
            break
        await client.sendall(data)
    print('Connection closed')

if __name__ == '__main__':
    kernel = Kernel()
    kernel.run(run_server('', 25000, echo_handler))
