# curio/zmq.py
#
# Curio support for ZeroMQ.   Requires pyzmq.

import pickle
from zmq.asyncio import ZMQSelector
from zmq.utils import jsonapi
import zmq

from .traps import _read_wait, _write_wait

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
    from . import kernel
    return kernel.run(selector=ZMQSelector(), *args, **kwargs)
