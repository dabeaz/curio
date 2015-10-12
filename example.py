import curio
from socket import *
from fib import fib
from concurrent.futures import ProcessPoolExecutor
import subprocess

pool = ProcessPoolExecutor()

async def fib_server(address):
    sock = curio.Socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    print('Waiting for connection')
    while True:
        client, addr = await sock.accept()
        print('Connection from', addr)
        kernel.add_task(fib_client(client))
        
async def fib_client(client):
    with client:
        while True:
            data = await client.recv(1000)
            if not data:
                break
            n = int(data)
            result = await kernel.run_in_executor(pool, fib, n)
            data = str(result).encode('ascii') + b'\n'
            await client.send(data)
    print('Connection closed')

async def udp_echo(address):
    sock = curio.Socket(AF_INET, SOCK_DGRAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
    sock.bind(address)
    
    while True:
        msg, addr = await sock.recvfrom(8192)
        print('Message from', addr)
        await sock.sendto(msg, addr)

async def spinner(prefix, interval):
    n = 0
    while True:
        await curio.sleep(interval)
        print(prefix, n)
        n += 1

async def subproc():
    p = subprocess.Popen(['python3', 'slow.py'], stdout=subprocess.PIPE)
    f = curio.File(p.stdout)
    while True:
        line = await f.readline()
        if not line:
            break
        print('subproc', line)
    print('Subproc done')

# Test socketserver

from curio.socketserver import TCPServer, UDPServer, BaseRequestHandler, StreamRequestHandler

class EchoHandler(BaseRequestHandler):
    async def handle(self):
        print('Echo connection from', self.client_address)
        while True:
            data = await self.request.recv(1000)
            if not data:
                break
            await self.request.sendall(b'Got:' + data)
        print('Client done')

server = TCPServer(('', 27000), EchoHandler)

class EchoUDPHandler(BaseRequestHandler):
    async def handle(self):
        print('Echo connection from', self.client_address)
        data, sock = self.request
        await sock.sendto(b'Got:' + data, self.client_address)

udpserver = UDPServer(('', 28000), EchoUDPHandler)

class EchoStreamHandler(StreamRequestHandler):
    async def handle(self):
          print('Echo connection from', self.client_address)
          while True:
              line = await self.rfile.readline()
              if not line:
                  break
              await self.wfile.write(b'Line:' + line)
          print('Client done')

eserver = TCPServer(('', 29000), EchoStreamHandler)

kernel = curio.get_kernel()
kernel.add_task(server.serve_forever())
kernel.add_task(eserver.serve_forever())
kernel.add_task(udpserver.serve_forever())
kernel.add_task(fib_server(('',25000)))
#kernel.add_task(spinner('spin1', 5))
#kernel.add_task(spinner('spin2', 1))
kernel.add_task(udp_echo(('',26000)))
kernel.add_task(subproc())
kernel.run(detached=True)

