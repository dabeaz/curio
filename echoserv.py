from curio import *
from socket import *
import signal

async def monitor():
    async with Signal(signal.SIGUSR1) as sig:
        while True:
             n = await sig.wait()
             print('Caught signal', n)
    print('Here')

async def echo_server(address):
    sock = Socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    while True:
        client, addr = await sock.accept()
        print('Connection from', addr)
        await new_task(echo_client(client))
        del client

async def echo_client(client):
    async with client.makefile('rwb') as client_f:
        async for line in client_f:
            await client_f.write(line)
    print('Connection closed')

if __name__ == '__main__':
    import os
    print('pid', os.getpid())
    kernel = get_kernel()
    kernel.add_task(echo_server(('',25000)))
    kernel.add_task(monitor())
    kernel.run()



    
