from curio import *
from socket import *
import signal

async def monitor():
    async with SignalSet(signal.SIGUSR1, signal.SIGUSR2) as sigset:
        while True:
             try:
                  signo = await sigset.wait(timeout=30)
                  print('Caught signal', signo)
             except TimeoutError:
                  print('No signal')
             except CancelledError:
                  print('Cancelled')
                  return

async def main(address):
    task = await new_task(echo_server(address))
    await SignalSet(signal.SIGINT).wait()
    print('You hit control-C')
    await task.cancel()
    print('Shutdown complete')

async def echo_server(address):
    sock = Socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    with sock:
        while True:
             client, addr = await sock.accept()
             print('Connection from', addr)
             await new_task(echo_client(client))
             del client

async def echo_client(client):
    with client.makefile('rwb') as client_f:
        try:
             async for line in client_f:
                 await client_f.write(line)
        except CancelledError:
             await client_f.write(b'Server going down\n')
             
    print('Connection closed')

if __name__ == '__main__':
    import os
    print('pid', os.getpid())
    kernel = get_kernel()
    kernel.add_task(main(('',25000)))
    kernel.add_task(monitor())
    kernel.run()



    
