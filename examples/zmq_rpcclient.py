# zmq RPC client example. Requires zmq_rpcserv.py to be runnig

import curio_zmq as zmq
from curio import sleep, spawn

from fibserve import fib

async def ticker():
    n = 0
    while True:
        await sleep(1)
        print('Tick:', n)
        n += 1

async def client(address):
    # Run a background task to make sure the message passing operations don't block
    await spawn(ticker, daemon=True)

    # Compute the first 40 fibonacci numbers
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(address)
    for n in range(1, 40):
        await sock.send_pyobj((fib, (n,), {}))
        result = await sock.recv_pyobj()
        print(n, result)

if __name__ == '__main__':
    zmq.run(client, 'tcp://localhost:9000')
