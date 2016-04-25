# Example: A simple Unix  echo server

from curio import boot, run_unix_server

async def echo_handler(client, address):
    print('Connection from', address)
    while True:
         data = await client.recv(10000)
         if not data:
              break
         await client.sendall(data)
    print('Connection closed')

if __name__ == '__main__':
     import os
     try:
          os.remove('/tmp/curiounixecho')
     except:
          pass
     boot(run_unix_server('/tmp/curiounixecho', echo_handler))
          
