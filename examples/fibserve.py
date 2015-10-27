# An example of a server involving a CPU-intensive task.  We'll farm the 
# CPU-intensive work out to a separate process.

from curio import Kernel, new_task, run_cpu_bound
from curio.socketserver import *

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

class FibHandler(StreamRequestHandler):
    async def handle(self):
        print('Connection from', self.client_address)
        async for line in self.rfile:
            try:
                n = int(line)
                result = await run_cpu_bound(fib, n)
                resp = str(result) + '\n'
                await self.wfile.write(resp.encode('ascii'))
            except ValueError:
                await self.wfile.write(b'Bad input\n')
        print('Connection closed')

if __name__ == '__main__':
    serv = TCPServer(('', 25000), FibHandler)
    kernel = Kernel()
    kernel.add_task(serv.serve_forever())
    kernel.run()



    
