# A Curio implementation of the zmq tests posted at:
#  https://github.com/achimnol/asyncio-zmq-benchmark

import time
import os
from curio import *
import curio.zmq as zmq

ctx = zmq.Context()

async def pushing():
    server = ctx.socket(zmq.PUSH)
    server.bind('tcp://*:9000')
    for i in range(5000):
        await server.send(b'Hello %d' % i)
    await server.send(b'exit')

async def pulling():
    client = ctx.socket(zmq.PULL)
    client.connect('tcp://127.0.0.1:9000')
    with open(os.devnull, 'w') as null:
        while True:
            greeting = await client.recv_multipart()
            if greeting[0] == b'exit': 
                break
            print(greeting[0], file=null)

async def main():
    t = await spawn(pushing())
    try:
        begin = time.monotonic()
        await pulling()
        end = time.monotonic()
        print('curio + pyzmq: {:.6f} sec.'.format(end - begin))
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    zmq.run(main())


