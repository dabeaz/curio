# zmq rpc example.

import curio.zmq as zmq

async def rpc_server(address):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REP)
    sock.bind(address)
    while True:
        func, args, kwargs = await sock.recv_pyobj()
        try:
            result = func(*args, **kwargs)
            await sock.send_pyobj(result)
        except Exception as e:
            await sock.send_pyobj(e)

if __name__ == '__main__':
    zmq.run(rpc_server('tcp://*:9000'))
