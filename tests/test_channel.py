# test_channel.py

import pytest
from socket import *
from curio.channel import Channel
from curio.io import Stream
from curio import new_task, sleep, CancelledError, TaskTimeout

@pytest.fixture
def chs():
    sock1, sock2 = socketpair()
    fileno1 = sock1.detach()
    ch1 = Channel(Stream(open(fileno1, 'rb', buffering=0)),
                  Stream(open(fileno1, 'wb', buffering=0, closefd=False)))

    fileno2 = sock2.detach()
    ch2 = Channel(Stream(open(fileno2, 'rb', buffering=0)),
                  Stream(open(fileno2, 'wb', buffering=0, closefd=False)))
    return (ch1, ch2)

def test_channel_hello(kernel, chs):
    results = []

    async def server(ch):
        async with ch:
            await ch.send('server hello world')
            results.append(await ch.recv())

    async def client(ch):
        async with ch:
            msg = await ch.recv()
            results.append(msg)
            await ch.send('client hello world')
        
    ch1, ch2 = chs
    kernel.add_task(server(ch1))
    kernel.add_task(client(ch2))
    kernel.run()
    assert results == [ 'server hello world',
                        'client hello world' ]

def test_channel_hello_bytes(kernel, chs):
    results = []

    async def server(ch):
        async with ch:
            await ch.send(b'server hello world')
            results.append(await ch.recv())

    async def client(ch):
        async with ch:
            msg = await ch.recv()
            results.append(msg)
            await ch.send(b'client hello world')
        
    ch1, ch2 = chs
    kernel.add_task(server(ch1))
    kernel.add_task(client(ch2))
    kernel.run()
    assert results == [ b'server hello world',
                        b'client hello world' ]

def test_channel_large(kernel, chs):
    results = []
    data = list(range(1000000))

    async def server(ch):
        async with ch:
            await ch.send(data)
            results.append(await ch.recv())

    async def client(ch):
        async with ch:
            msg = await ch.recv()
            results.append(msg)
            await ch.send(len(msg))
        
    ch1, ch2 = chs
    kernel.add_task(server(ch1))
    kernel.add_task(client(ch2))
    kernel.run()
    assert results == [ data,
                        len(data) ]

def test_channel_auth(kernel, chs):
    results = []

    async def server(ch):
        async with ch:
            await ch.authenticate_server(b'peekaboo')
            await ch.send('server hello world')
            results.append(await ch.recv())

    async def client(ch):
        async with ch:
            await ch.authenticate_client(b'peekaboo')
            msg = await ch.recv()
            results.append(msg)
            await ch.send('client hello world')
        
    ch1, ch2 = chs
    kernel.add_task(server(ch1))
    kernel.add_task(client(ch2))
    kernel.run()
    assert results == [ 'server hello world',
                        'client hello world' ]

def test_channel_send_partial_bytes(kernel, chs):
    results = []
    data = b'abcdefghijklmnopqrstuvwxyz'

    async def server(ch):
        async with ch:
            await ch.send_bytes(data, offset=5, size=10)
            results.append(await ch.recv())
            await ch.send_bytes(data, offset=5)
            results.append(await ch.recv())
            await ch.send_bytes(data, size=10)
            results.append(await ch.recv())

            # Try some bad inputs
            try:
                await ch.send_bytes(data, offset=50)
            except ValueError as e:
                results.append(str(e))

            try:
                await ch.send_bytes(data, size=50)
            except ValueError as e:
                results.append(str(e))

            try:
                await ch.send_bytes(data, offset=-10)
            except ValueError as e:
                results.append(str(e))

            try:
                await ch.send_bytes(data, size=-10)
            except ValueError as e:
                results.append(str(e))

    async def client(ch):
        async with ch:
            msg = await ch.recv_bytes()
            results.append(msg)
            await ch.send(len(msg))
            msg = await ch.recv_bytes()
            results.append(msg)
            await ch.send(len(msg))
            msg = await ch.recv_bytes()
            results.append(msg)
            await ch.send(len(msg))
        
    ch1, ch2 = chs
    kernel.add_task(server(ch1))
    kernel.add_task(client(ch2))
    kernel.run()
    assert results == [ data[5:15], 10,
                        data[5:], len(data[5:]),
                        data[:10], 10,
                        'buffer length < offset',
                        'buffer length < offset + size',
                        'offset is negative',
                        'size is negative',

                        ]

def test_channel_from_connection(kernel):
    import multiprocessing
    p1, p2 = multiprocessing.Pipe()
    ch1 = Channel.from_Connection(p1)
    ch2 = Channel.from_Connection(p2)
    
    results = []

    async def server(ch):
        async with ch:
            await ch.send('server hello world')
            results.append(await ch.recv())

    async def client(ch):
        async with ch:
            msg = await ch.recv()
            results.append(msg)
            await ch.send('client hello world')
        
    kernel.add_task(server(ch1))
    kernel.add_task(client(ch2))
    kernel.run()
    assert results == [ 'server hello world',
                        'client hello world' ]


def test_channel_recv_cancel(kernel, chs):
    results = []

    async def client(ch):
        async with ch:
            try:
                msg = await ch.recv()
                results.append(msg)
            except CancelledError:
                results.append('cancel')

    async def main(ch):
        task = await new_task(client(ch))
        await sleep(1)
        await task.cancel()
        results.append('done cancel')

    ch1, ch2 = chs
    task = kernel.add_task(main(ch2))
    kernel.run()
    assert results == [ 'cancel', 'done cancel' ]


def test_channel_recv_timeout(kernel, chs):
    results = []

    async def client(ch):
        with ch.timeout(1):
            try:
                msg = await ch.recv()
                results.append(msg)
            except TaskTimeout:
                results.append('timeout')

    async def main(ch):
        task = await new_task(client(ch))
        await task.join()
        results.append('done')

    ch1, ch2 = chs
    task = kernel.add_task(main(ch2))
    kernel.run()
    assert results == [ 'timeout', 'done' ]

def test_channel_send_cancel(kernel, chs):
    results = []

    async def client(ch):
        async with ch:
            try:
                msg = 'x'*10000000   # Should be large enough to cause send blocking
                await ch.send(msg)
                results.append('success')
            except CancelledError:
                results.append('cancel')

    async def main(ch):
        task = await new_task(client(ch))
        await sleep(1)
        await task.cancel()
        results.append('done cancel')

    ch1, ch2 = chs
    task = kernel.add_task(main(ch2))
    kernel.run()
    assert results == [ 'cancel', 'done cancel' ]


def test_channel_send_timeout(kernel, chs):
    results = []

    async def client(ch):
        with ch.timeout(1):
            try:
                msg = 'x'*10000000
                await ch.send(msg)
                results.append('success')
            except TaskTimeout:
                results.append('timeout')

    async def main(ch):
        task = await new_task(client(ch))
        await task.join()
        results.append('done')

    ch1, ch2 = chs
    task = kernel.add_task(main(ch2))
    kernel.run()
    assert results == [ 'timeout', 'done' ]
