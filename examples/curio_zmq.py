# curio_zmq.py
#
# Curio support for ZeroMQ.   Requires pyzmq.
'''
ZeroMQ wrapper module
---------------------

The curio_zmq module provides an async wrapper around the third party
pyzmq library for communicating via ZeroMQ.   You use it in the same way except
that certain operations are replaced by async functions.

Context(*args, **kwargs)

   An asynchronous subclass of zmq.Context. It has the same arguments
   and methods as the synchronous class.   Create ZeroMQ sockets using the
   socket() method of this class.

Sockets created by the curio_zmq.Context() class have the following
methods replaced by asynchronous versions:

   Socket.send(data, flags=0, copy=True, track=False)
   Socket.recv(flags=0, copy=True, track=False)
   Socket.send_multipart(msg_parts, flags=0, copy=True, track=False)
   Socket.recv_multipart(flags=0, copy=True, track=False)
   Socket.send_pyobj(obj, flags=0, protocol=pickle.DEFAULT_PROTOCOL)
   Socket.recv_pyobj(flags=0)
   Socket.send_json(obj, flags=0, **kwargs)
   Socket.recv_json(flags, **kwargs)
   Socket.send_string(u, flags=0, copy=True, encoding='utf-8')
   Socket.recv_string(flags=0, encoding='utf-8')

To run a Curio application that uses ZeroMQ, a special selector must be given
to the Kernel.  You can either do this::

   from curio_zmq import ZMQSelector
   from curio import run

   async def main():
       ...

   run(main(), selector=ZMQSelector())

Alternative, you can use the ``curio_zmq.run()`` function like this::

   from curio_zmq import run

   async def main():
       ...

   run(main())

Here is an example of task that uses a ZMQ PUSH socket::

    import curio_zmq as zmq

    async def pusher(address):
        ctx = zmq.Context()
        sock = ctx.socket(zmq.PUSH)
        sock.bind(address)
        for n in range(100):
            await sock.send(b'Message %d' % n)
        await sock.send(b'exit')

    if __name__ == '__main__':
        zmq.run(pusher('tcp://*:9000'))

Here is an example of a Curio task that receives messages::

    import curio_zmq as zmq

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
        zmq.run(puller('tcp://localhost:9000'))
'''

import pickle
from zmq.asyncio import ZMQSelector
from zmq.utils import jsonapi
import zmq

from curio.traps import _read_wait, _write_wait

# Pull all ZMQ constants and exceptions into our namespace
globals().update((key, val) for key, val in vars(zmq).items()
                 if key.isupper() or 
                    (isinstance(val, type) and issubclass(val, zmq.ZMQBaseError)))

class CurioZMQSocket(zmq.Socket):

    async def send(self, data, flags=0, copy=True, track=False):
        while True:
            try:
                return super().send(data, flags | zmq.NOBLOCK, copy, track)
            except zmq.Again:
                await _write_wait(self)

    async def recv(self, flags=0, copy=True, track=False):
         while True:
             try:
                 return super().recv(flags | zmq.NOBLOCK, copy, track)
             except zmq.Again:
                 await _read_wait(self)

    async def send_multipart(self, msg_parts, flags=0, copy=True, track=False):
        for msg in msg_parts[:-1]:
            await self.send(msg, zmq.SNDMORE | flags, copy=copy, track=track)
        return await self.send(msg_parts[-1], flags, copy=copy, track=track)

    async def recv_multipart(self, flags=0, copy=True, track=False):
         parts = [ await self.recv(flags, copy=copy, track=track) ]
         while self.getsockopt(zmq.RCVMORE):
             parts.append(await self.recv(flags, copy=copy, track=track))
         return parts

    async def send_pyobj(self, obj, flags=0, protocol=pickle.DEFAULT_PROTOCOL):
        return await self.send(pickle.dumps(obj, protocol), flags)

    async def recv_pyobj(self, flags=0):
        return pickle.loads(await self.recv(flags))

    async def send_json(self, obj, flags=0, **kwargs):
        return await self.send(jsonapi.dumps(obj, **kwargs), flags)

    async def recv_json(self, flags, **kwargs):
        return jsonapi.loads(await self.recv(flags), **kwargs)

    async def send_string(self, u, flags=0, copy=True, encoding='utf-8'):
        return await self.send(u.encode(encoding), flags=flags, copy=copy)

    async def recv_string(self, flags=0, encoding='utf-8'):
        return (await self.recv(flags=flags)).decode(encoding)

class Context(zmq.Context):
    _socket_class = CurioZMQSocket

def run(*args, **kwargs):
    '''
    Replacement for the Curio run() function that uses ZMQSelector.
    '''
    from curio import kernel
    return kernel.run(selector=ZMQSelector(), *args, **kwargs)
