from curio import Scheduler
from socket import *
from fib import fib
from concurrent.futures import ProcessPoolExecutor

pool = ProcessPoolExecutor()

async def fib_server(address):
    sock = socket(AF_INET, SOCK_STREAM)
    sock.setblocking(False)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    print('Waiting for connection')
    while True:
        client, addr = await sched.sock_accept(sock)
        print('Connection from', addr)
        sched.add_task(fib_client(client))
        
async def fib_client(client):
    while True:
        data = await sched.sock_recv(client, 1000)
        if not data:
            break
        n = int(data)
        result = await sched.run_in_executor(pool, fib, n)
        data = str(result).encode('ascii') + b'\n'
        await sched.sock_sendall(client, data)
    print('Connection closed')
    client.close()

async def spinner(prefix, interval):
    n = 0
    while True:
        await sched.sleep(interval)
        print(prefix, n)
        n += 1

sched = Scheduler()
sched.add_task(fib_server(('',25000)))
sched.add_task(spinner('spin1', 5))
sched.add_task(spinner('spin2', 1))
sched.run()
