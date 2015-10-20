from curio import socketserver, get_kernel

class EchoHandler(socketserver.BaseRequestHandler):
    async def handle(self):
        print('Connection from', self.client_address)
        while True:
             data = await self.request.recv(1000)
             if not data:
                  break
             await self.request.sendall(data)
        print('Connection closed')

class EchoStreamHandler(socketserver.StreamRequestHandler):
     async def handle(self):
         print('Connection from', self.client_address)
         async for line in self.rfile:
             await self.wfile.write(line)
         print('Connection closed')

if __name__ == '__main__':
     server1 = socketserver.TCPServer(('',25000), EchoHandler)
     server2 = socketserver.TCPServer(('',26000), EchoStreamHandler)
     kernel = get_kernel()
     kernel.add_task(server1.serve_forever())
     kernel.add_task(server2.serve_forever())
     kernel.run()


    
