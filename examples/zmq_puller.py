# zmq pull client example.  Requires zmq_pusher.py to be running

import curio.zmq as zmq

async def puller(address):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    sock.connect(address)
    while True:
        msg = await sock.recv()
        if msg == b'exit':
            break
        print('Got:', msg)

if __name__ == '__main__':
    zmq.run(puller, 'tcp://localhost:9000')
