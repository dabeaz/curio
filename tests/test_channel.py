# test_channel.py

import pytest
from socket import *
from curio.channel import Connection, Channel, AuthenticationError
from curio.io import SocketStream
from curio import spawn, sleep, CancelledError, TaskTimeout, timeout_after, TaskError
import copy

@pytest.fixture
def conns():
    sock1, sock2 = socketpair()
    sock1_s = SocketStream(sock1)
    sock2_s = SocketStream(sock2)
    c1 = Connection(sock1_s, sock1_s)
    c2 = Connection(sock2_s, sock2_s)
    return (c1, c2)

def test_connection_hello(kernel, conns):
    results = []

    async def server(c):
        async with c:
            await c.send('server hello world')
            results.append(await c.recv())

    async def client(c):
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send('client hello world')

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(*conns))
    assert results == ['server hello world',
                       'client hello world']


def test_connection_hello_bytes(kernel, conns):
    results = []

    async def server(c):
        async with c:
            await c.send(b'server hello world')
            results.append(await c.recv())

    async def client(c):
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send(b'client hello world')

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(*conns))
    assert results == [b'server hello world',
                       b'client hello world']


def test_connection_large(kernel, conns):
    results = []
    data = list(range(1000000))

    async def server(c):
        async with c:
            await c.send(data)
            results.append(await c.recv())

    async def client(c):
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send(len(msg))

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(*conns))
    assert results == [data,
                       len(data)]


def test_connection_auth(kernel, conns):
    results = []

    async def server(c):
        async with c:
            await c.authenticate_server(b'peekaboo')
            await c.send('server hello world')
            results.append(await c.recv())

    async def client(c):
        async with c:
            await c.authenticate_client(b'peekaboo')
            msg = await c.recv()
            results.append(msg)
            await c.send('client hello world')

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(*conns))

    assert results == ['server hello world',
                       'client hello world']



def test_connection_auth_fail(kernel, conns):
    async def server(c):
        async with c:
            with pytest.raises(AuthenticationError):
                await c.authenticate_server(b'peekaboo')

    async def client(c):
        async with c:
            with pytest.raises(AuthenticationError):
                await c.authenticate_client(b'what?')

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(*conns))


def test_connection_send_partial_bytes(kernel, conns):
    results = []
    data = b'abcdefghijklmnopqrstuvwxyz'

    async def server(c):
        async with c:
            await c.send_bytes(data, offset=5, size=10)
            results.append(await c.recv())
            await c.send_bytes(data, offset=5)
            results.append(await c.recv())
            await c.send_bytes(data, size=10)
            results.append(await c.recv())

            # Try some bad inputs
            try:
                await c.send_bytes(data, offset=50)
            except ValueError as e:
                results.append(str(e))

            try:
                await c.send_bytes(data, size=50)
            except ValueError as e:
                results.append(str(e))

            try:
                await c.send_bytes(data, offset=-10)
            except ValueError as e:
                results.append(str(e))

            try:
                await c.send_bytes(data, size=-10)
            except ValueError as e:
                results.append(str(e))

    async def client(c):
        async with c:
            msg = await c.recv_bytes()
            results.append(msg)
            await c.send(len(msg))
            msg = await c.recv_bytes()
            results.append(msg)
            await c.send(len(msg))
            msg = await c.recv_bytes()
            results.append(msg)
            await c.send(len(msg))

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(*conns))
    assert results == [data[5:15], 10,
                       data[5:], len(data[5:]),
                       data[:10], 10,
                       'buffer length < offset',
                       'buffer length < offset + size',
                       'offset is negative',
                       'size is negative',

                       ]


def test_connection_from_connection(kernel):
    import multiprocessing
    p1, p2 = multiprocessing.Pipe()
    c1 = Connection.from_Connection(p1)
    c2 = Connection.from_Connection(p2)

    results = []

    async def server(c):
        async with c:
            await c.send('server hello world')
            results.append(await c.recv())

    async def client(c):
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send('client hello world')

    async def main(c1, c2):
        await spawn(server, c1)
        await spawn(client, c2)

    kernel.run(main(c1, c2))
    assert results == ['server hello world',
                       'client hello world']


def test_connection_recv_cancel(kernel, conns):
    results = []

    async def client(c):
        async with c:
            try:
                msg = await c.recv()
                results.append(msg)
            except CancelledError:
                results.append('cancel')

    async def main(c):
        task = await spawn(client, c)
        await sleep(1)
        await task.cancel()
        results.append('done cancel')

    c1, c2 = conns
    kernel.run(main(c2))
    assert results == ['cancel', 'done cancel']


def test_connection_recv_timeout(kernel, conns):
    results = []

    async def client(c):
        try:
            msg = await timeout_after(1.0, c.recv())
            results.append(msg)
        except TaskTimeout:
            results.append('timeout')

    async def main(c):
        task = await spawn(client, c)
        await task.join()
        results.append('done')

    c1, c2 = conns
    kernel.run(main(c2))
    assert results == ['timeout', 'done']


def test_connection_send_cancel(kernel, conns):
    results = []

    async def client(c):
        async with c:
            try:
                msg = 'x' * 10000000   # Should be large enough to cause send blocking
                await c.send(msg)
                results.append('success')
            except CancelledError:
                results.append('cancel')

    async def main(c):
        task = await spawn(client, c)
        await sleep(1)
        await task.cancel()
        results.append('done cancel')

    c1, c2 = conns
    kernel.run(main(c2))
    assert results == ['cancel', 'done cancel']


def test_connection_send_timeout(kernel, conns):
    results = []

    async def client(c):
        try:
            msg = 'x' * 10000000
            await timeout_after(1, c.send(msg))
            results.append('success')
        except TaskTimeout:
            results.append('timeout')

    async def main(c):
        task = await spawn(client, c)
        await task.join()
        results.append('done')

    c1, c2 = conns
    kernel.run(main(c2))
    assert results == ['timeout', 'done']


@pytest.fixture
def chs():
    ch1 = Channel(('localhost', 0))
    ch1.bind()
    ch2 = copy.deepcopy(ch1)
    return ch1, ch2

def test_channel_hello(kernel, chs):
    results = []

    async def server(ch):
        c = await ch.accept()
        async with c:
            await c.send('server hello world')
            results.append(await c.recv())

    async def client(ch):
        c = await ch.connect()
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send('client hello world')

    async def main(ch1, ch2):
        await spawn(server, ch1)
        await spawn(client, ch2)

    kernel.run(main(*chs))
    assert results == ['server hello world',
                       'client hello world']


def test_channel_hello_auth(kernel, chs):
    results = []

    async def server(ch):
        c = await ch.accept(authkey=b'peekaboo')
        async with c:
            await c.send('server hello world')
            results.append(await c.recv())

    async def client(ch):
        c = await ch.connect(authkey=b'peekaboo')
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send('client hello world')

    async def main(ch1, ch2):
        await spawn(server, ch1)
        await spawn(client, ch2)

    kernel.run(main(*chs))
    assert results == ['server hello world',
                       'client hello world']


def test_channel_hello_auth_fail(kernel, chs):

    async def server(ch):
        c = await ch.accept(authkey=b'peekaboo')
        async with c:
            await c.send('server hello world')

    async def client(ch):
        with pytest.raises(AuthenticationError):
            c = await ch.connect(authkey=b'what?')

    async def main(ch1, ch2):
        t1 = await spawn(server, ch1)
        t2 = await spawn(client, ch2)
        await t2.join()
        await t1.cancel()

    kernel.run(main(*chs))

@pytest.mark.skip
def test_channel_slow_connect(kernel, chs):
    results = []

    async def server(ch):
        await sleep(2)
        c = await ch.accept(authkey=b'peekaboo')
        async with c:
            await c.send('server hello world')
            results.append(await c.recv())

    async def client(ch):
        c = await ch.connect(authkey=b'peekaboo')
        async with c:
            msg = await c.recv()
            results.append(msg)
            await c.send('client hello world')

    async def main(ch1, ch2):
        async with ch1, ch2:
            t1 = await spawn(server, ch1)
            t2 = await spawn(client, ch2)
            await t1.join()
            await t2.join()

    kernel.run(main(*chs))
    assert results == ['server hello world',
                       'client hello world']

