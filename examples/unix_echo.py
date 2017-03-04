# Example: A simple Unix  echo server

from curio import run, unix_server


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
    try:
        run(unix_server, '/tmp/curiounixecho', echo_handler)
    except KeyboardInterrupt:
        pass
