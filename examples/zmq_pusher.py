# zmq push example. Run the zmq_puller.py program for the client

import curio_zmq as zmq

async def pusher(address):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.bind(address)
    for n in range(100):
        await sock.send(b'Message %d' % n)
    await sock.send(b'exit')

if __name__ == '__main__':
    zmq.run(pusher, 'tcp://*:9000')
