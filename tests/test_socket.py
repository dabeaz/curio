# test_socket.py

import os

from curio import *
from curio.socket import *
from curio import io
import pytest
import sys

def test_tcp_echo(kernel, portno):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(5)
        results.append('accept wait')
        client, addr = await sock.accept()
        results.append('accept done')
        await spawn(handler, client)
        await sock.close()

    async def handler(client):
        results.append('handler start')
        while True:
            results.append('recv wait')
            data = await client.recv(100)
            if not data:
                break
            results.append(('handler', data))
            await client.sendall(data)
        results.append('handler done')
        await client.close()

    async def client(address):
        results.append('client start')
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.send(b'Msg1')
        await sleep(0.1)
        resp = await sock.recv(100)
        results.append(('client', resp))
        await sock.send(b'Msg2')
        await sleep(0.1)
        resp = await sock.recv(100)
        results.append(('client', resp))
        results.append('client close')
        await sock.close()

    async def main():
        async with TaskGroup() as g:
            await g.spawn(server, ('', portno))
            await g.spawn(client, ('localhost', portno))

    kernel.run(main())

    assert results == [
        'accept wait',
        'client start',
        'accept done',
        'handler start',
        'recv wait',
        ('handler', b'Msg1'),
        'recv wait',
        ('client', b'Msg1'),
        ('handler', b'Msg2'),
        'recv wait',
        ('client', b'Msg2'),
        'client close',
        'handler done'
    ]


def test_tcp_file_echo(kernel, portno):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(5)
        results.append('accept wait')
        client, addr = await sock.accept()
        results.append('accept done')
        await spawn(handler, client)
        await sock.close()

    async def handler(client):
        results.append('handler start')
        stream = client.as_stream()
        async for line in stream:
            results.append(('handler', line))
            await stream.write(line)
        results.append('handler done')
        await client.close()

    async def client(address):
        results.append('client start')
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        stream = sock.as_stream()
        await stream.write(b'Msg1\n')
        await sleep(0.1)
        resp = await stream.read(100)
        results.append(('client', resp))
        await stream.write(b'Msg2\n')
        await sleep(0.1)
        resp = await stream.read(100)
        results.append(('client', resp))
        results.append('client close')
        await sock.close()

    async def main():
        async with TaskGroup() as g:
             await g.spawn(server, ('', portno))
             await g.spawn(client, ('localhost', portno))

    kernel.run(main())

    assert results == [
        'accept wait',
        'client start',
        'accept done',
        'handler start',
        ('handler', b'Msg1\n'),
        ('client', b'Msg1\n'),
        ('handler', b'Msg2\n'),
        ('client', b'Msg2\n'),
        'client close',
        'handler done'
    ]


def test_udp_echo(kernel):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        results.append('recvfrom wait')
        data, addr = await sock.recvfrom(8192)
        results.append(('server', data))
        await sock.sendto(data, addr)
        await sock.close()
        results.append('server close')

    async def client(address):
        results.append('client start')
        sock = socket(AF_INET, SOCK_DGRAM)
        results.append('client send')
        await sock.sendto(b'Msg1', address)
        data, addr = await sock.recvfrom(8192)
        results.append(('client', data))
        await sock.close()
        results.append('client close')

    async def main():
        async with TaskGroup() as g:
            await g.spawn(server, ('', 25000))
            await g.spawn(client, ('localhost', 25000))

    kernel.run(main())

    assert results == [
        'recvfrom wait',
        'client start',
        'client send',
        ('server', b'Msg1'),
        'server close',
        ('client', b'Msg1'),
        'client close'
    ]

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason='currently broken')

def test_fromfd_tcp_echo(kernel, portno):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(5)
        results.append('accept wait')
        client, addr = await sock.accept()
        results.append('accept done')
        await spawn(handler, client.detach())
        await sock.close()

    async def handler(fileno):
        client = fromfd(fileno, AF_INET, SOCK_STREAM)
        results.append('handler start')
        while True:
            results.append('recv wait')
            data = await client.recv(100)
            if not data:
                break
            results.append(('handler', data))
            await client.sendall(data)
        results.append('handler done')
        await client.close()

    async def client(address):
        results.append('client start')
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.send(b'Msg1')
        await sleep(0.1)
        resp = await sock.recv(100)
        results.append(('client', resp))
        await sock.send(b'Msg2')
        await sleep(0.1)
        resp = await sock.recv(100)
        results.append(('client', resp))
        results.append('client close')
        await sock.close()

    async def main():
        async with TaskGroup() as g:
            await g.spawn(server, ('', portno))
            await g.spawn(client, ('localhost', portno))

    kernel.run(main())

    assert results == [
        'accept wait',
        'client start',
        'accept done',
        'handler start',
        'recv wait',
        ('handler', b'Msg1'),
        'recv wait',
        ('client', b'Msg1'),
        ('handler', b'Msg2'),
        'recv wait',
        ('client', b'Msg2'),
        'client close',
        'handler done'
    ]


def test_accept_timeout(kernel, portno):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(1)
        results.append('accept wait')
        try:
            client, addr = await timeout_after(0.5, sock.accept())
            results.append('not here')
        except TaskTimeout:
            results.append('accept timeout')
        await sock.close()

    kernel.run(server(('', portno)))

    assert results == [
        'accept wait',
        'accept timeout'
    ]


def test_accept_cancel(kernel, portno):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(1)
        results.append('accept wait')
        try:
            client, addr = await sock.accept()
            results.append('not here')
        except CancelledError:
            results.append('accept cancel')
        await sock.close()

    async def canceller():
        task = await spawn(server, ('', portno))
        await sleep(0.5)
        await task.cancel()

    kernel.run(canceller())
    assert results == [
        'accept wait',
        'accept cancel'
    ]


def test_recv_timeout(kernel):
    results = []
    async def server(address, accepting_event):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(1)
        results.append('accept wait')
        await accepting_event.set()
        client, addr = await sock.accept()
        results.append('recv wait')
        try:
            data = await timeout_after(0.5, client.recv(8192))
            results.append('not here')
        except TaskTimeout:
            results.append('recv timeout')
        await client.close()
        await sock.close()

    async def canceller():
        accepting_event = Event()
        task = await spawn(server, ('', 25000), accepting_event)
        await accepting_event.wait()
        sock = socket(AF_INET, SOCK_STREAM)
        results.append('client connect')
        await sock.connect(('localhost', 25000))
        await sleep(1.0)
        await sock.close()
        results.append('client done')
        await task.join()

    kernel.run(canceller())

    assert results == [
        'accept wait',
        'client connect',
        'recv wait',
        'recv timeout',
        'client done'
    ]


def test_recv_cancel(kernel):
    results = []
    async def server(address, accepting_event):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        sock.listen(1)
        results.append('accept wait')
        await accepting_event.set()
        client, addr = await sock.accept()
        results.append('recv wait')
        try:
            data = await client.recv(8192)
            results.append('not here')
        except CancelledError:
            results.append('recv cancel')
        await client.close()
        await sock.close()

    async def canceller():
        accepting_event = Event()
        task = await spawn(server, ('', 25000), accepting_event)
        await accepting_event.wait()
        sock = socket(AF_INET, SOCK_STREAM)
        results.append('client connect')
        await sock.connect(('localhost', 25000))
        await sleep(1.0)
        await task.cancel()
        await sock.close()
        results.append('client done')

    kernel.run(canceller())

    assert results == [
        'accept wait',
        'client connect',
        'recv wait',
        'recv cancel',
        'client done'
    ]


def test_recvfrom_timeout(kernel):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        results.append('recvfrom wait')
        try:
            await timeout_after(0.5, sock.recvfrom(8192))
            results.append('not here')
        except TaskTimeout:
            results.append('recvfrom timeout')
        await sock.close()

    async def canceller():
        t = await spawn(server, ('', 25000))
        await sleep(1.0)
        results.append('client done')
        await t.join()

    kernel.run(canceller())

    assert results == [
        'recvfrom wait',
        'recvfrom timeout',
        'client done'
    ]


def test_recvfrom_cancel(kernel):
    results = []
    async def server(address):
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(address)
        results.append('recvfrom wait')
        try:
            await sock.recvfrom(8192)
            results.append('not here')
        except CancelledError:
            results.append('recvfrom cancel')
        await sock.close()

    async def canceller():
        task = await spawn(server, ('', 25000))
        await sleep(1.0)
        await task.cancel()
        results.append('client done')

    kernel.run(canceller())

    assert results == [
        'recvfrom wait',
        'recvfrom cancel',
        'client done'
    ]


def test_buffer_into(kernel):
    from array import array
    results = []
    async def sender(s1):
        a = array('i', range(1000000))
        await s1.sendall(a)

    async def receiver(s2):
        a = array('i', (0 for n in range(1000000)))
        view = memoryview(a).cast('B')
        total = 0
        while view:
            nrecv = await s2.recv_into(view)
            if not nrecv:
                break
            total += nrecv
            view = view[nrecv:]

        results.append(a)

    s1, s2 = socketpair()

    async def main():
        async with TaskGroup() as g:
            await g.spawn(sender, s1)
            await g.spawn(receiver, s2)

    kernel.run(main())
    s1._socket.close()
    s2._socket.close()

    assert all(n == x for n, x in enumerate(results[0]))


def test_buffer_stream_into(kernel):
    from array import array
    results = []
    async def sender(s1):
        a = array('i', range(1000000))
        await s1.sendall(b'Hello world\n')
        await s1.sendall(a)

    async def receiver(s2):
        a = array('i', (0 for n in range(1000000)))
        view = memoryview(a).cast('B')
        total = 0
        s2_stream = s2.as_stream()
        assert isinstance(s2_stream, io.SocketStream)
        line = await s2_stream.readline()
        assert line == b'Hello world\n'
        while view:
            nrecv = await s2_stream.readinto(view)
            if not nrecv:
                break
            total += nrecv
            view = view[nrecv:]

        results.append(a)

    s1, s2 = socketpair()

    async def main():
        async with TaskGroup() as g:
            await g.spawn(sender, s1)
            await g.spawn(receiver, s2)

    kernel.run(main())
    s1._socket.close()
    s2._socket.close()

    assert all(n == x for n, x in enumerate(results[0]))

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason='broken on Windows')
def test_buffer_makefile_into(kernel):
    from array import array
    results = []
    async def sender(s1):
        a = array('i', range(1000000))
        await s1.sendall(b'Hello world\n')
        await s1.sendall(a)

    async def receiver(s2):
        a = array('i', (0 for n in range(1000000)))
        view = memoryview(a).cast('B')
        total = 0
        s2_file = s2.makefile('rb')
        assert isinstance(s2_file, io.FileStream)

        line = await s2_file.readline()
        assert line == b'Hello world\n'
        while view:
            nrecv = await s2_file.readinto(view)
            if not nrecv:
                break
            total += nrecv
            view = view[nrecv:]

        results.append(a)

    s1, s2 = socketpair()

    async def main():
        async with TaskGroup() as g:
            await g.spawn(sender, s1)
            await g.spawn(receiver, s2)

    kernel.run(main())
    s1._socket.close()
    s2._socket.close()

    assert all(n == x for n, x in enumerate(results[0]))



def test_read_write_on_same_socket(kernel):
    async def main():
        s1, s2 = socketpair()
        t1 = await spawn(s1.recv, 1000)
        # Large enough send to trigger blocking on write:
        N = 10000000
        t2 = await spawn(s1.sendall, b"x" * N)
        # Above is the actual test -- right now it triggers a crash.
        # Rest of this is just to clean up:
        # Let t1 finish:
        await s2.sendall(b"x")
        # Let t2 finish:
        n = 0
        while n < N:
            n += len(await s2.recv(N))
        await t1.join()
        await t2.join()

    kernel.run(main())

def test_create_connection(kernel):
    evt = Event()
    async def server(addr):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(addr)
        sock.listen(1)
        await evt.set()
        client, addr = await sock.accept()
        assert addr[1] == 25001
        await client.close()
        await sock.close()

    async def client(servaddr, clientaddr):
        await evt.wait()
        sock = await create_connection(servaddr, source_address=clientaddr)
        await sock.close()

    async def main():
        async with TaskGroup() as g:
            await g.spawn(server, ('', 25000))
            await sleep(0.1)
            await g.spawn(client, ('localhost', 25000), ('localhost', 25001))
        assert not any(g.exceptions)

    kernel.run(main)

def test_create_bad_connection(kernel):
    async def main():
        with pytest.raises(OSError):
            await create_connection(('python.org', 1))

    kernel.run(main)

# Smoke test on various socket functions
@pytest.mark.skipif(True,
                    reason='unreliable')
def test_socket_funcs(kernel):
    async def main():
        r = await getaddrinfo('', 80)
        r = await getfqdn('')
        r = await gethostbyname('127.0.0.1')
        r = await gethostbyname_ex('127.0.0.1')
        r = await gethostname()
        r = await gethostbyaddr('127.0.0.1')
        r = await getnameinfo(('127.0.0.1', 80), NI_NUMERICHOST)
    kernel.run(main)

