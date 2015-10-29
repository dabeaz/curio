# Example: A simple Unix  echo server

from curio import Kernel, run_unix_server

async def echo_handler(client, address):
    print('Connection from', address)
    while True:
         data = await client.recv(10000)
         if not data:
              break
         await client.sendall(data)
    print('Connection closed')

if __name__ == '__main__':
     kernel = Kernel(with_monitor=True)
     import os
     try:
          os.remove('/tmp/curiounixecho')
     except:
          pass
     kernel.run(run_unix_server('/tmp/curiounixecho', echo_handler))
          
