# test_io.py

from curio import *
from curio.socket import *
import io
import socket as std_socket
import pytest
import sys

def test_socket_blocking(kernel, portno):
    '''
    Test of exposing a socket in blocking mode
    '''
    done = Event()

    results = []

    def sync_client(sock):
        assert isinstance(sock, std_socket.socket)
        data = sock.recv(8192)
        results.append(('client', data))
        sock.sendall(data)

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        with client.blocking() as s:
            await run_in_thread(sync_client, s)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Message')
        data = await sock.recv(8192)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()


    kernel.run(main())

    assert results == [
        'handler start',
        ('client', b'Message'),
        'handler done'
    ]

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="not supported on Windows")
def test_socketstream_blocking(kernel, portno):
    '''
    Test of exposing a socket stream in blocking mode
    '''
    done = Event()
    results = []

    def sync_client(f):
        assert isinstance(f, io.RawIOBase)
        data = f.read(8192)
        results.append(('client', data))
        f.write(data)

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        with s.blocking() as f:
            await run_in_thread(sync_client, f)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Message')
        data = await sock.recv(8192)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        ('client', b'Message'),
        'handler done'
    ]

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="not supported on Windows")
def test_filestream_blocking(kernel, portno):
    '''
    Test of exposing a socket in blocking mode
    '''
    done = Event()
    results = []

    def sync_client(f):
        assert isinstance(f, io.RawIOBase)
        data = f.read(8192)
        results.append(('client', data))
        f.write(data)

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.makefile('rwb', buffering=0)
        with s.blocking() as f:
            await run_in_thread(sync_client, f)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Message')
        data = await sock.recv(8192)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        ('client', b'Message'),
        'handler done'
    ]

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="not supported on Windows")
def test_filestream_bad_blocking(kernel, portno):
    '''
    Test of exposing a socket in blocking mode with buffered data error
    '''
    done = Event()
    results = []

    async def handler(client, addr):
        await client.send(b'OK')
        s = client.makefile('rwb', buffering=0)
        line = await s.readline()
        assert line == b'hello\n'
        try:
            with s.blocking() as f:
                pass
        except IOError:
            results.append(True)
        else:
            results.append(False)
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'hello\nworld\n')
        data = await sock.recv(8192)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())
    assert results[0]

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="not supported on Windows")
def test_socketstream_bad_blocking(kernel, portno):
    '''
    Test of exposing a socket in blocking mode with buffered data error
    '''
    done = Event()
    results = []

    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        line = await s.readline()
        assert line == b'hello\n'
        try:
            with s.blocking() as f:
                pass
        except IOError:
            results.append(True)
        else:
            results.append(False)
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'hello\nworld\n')
        data = await sock.recv(8192)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())
    assert results[0]

def test_read_partial(kernel, portno):
    done = Event()
    results = []
    async def handler(client, addr):
        try:
            await client.send(b'OK')
            s = client.as_stream()
            line = await s.readline()
            results.append(line)
            data = await s.read(2)
            results.append(data)
            data = await s.read(1000)
            results.append(data)
        finally:
            await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'hello\nworld\n')
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())
    assert results == [ b'hello\n', b'wo', b'rld\n']

def test_readall(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        async with client.as_stream() as s:
            data = await s.readall()
            results.append(data)
            results.append('handler done')
            await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\n')
        await sleep(0.1)
        await sock.send(b'Msg2\n')
        await sleep(0.1)
        await sock.send(b'Msg3\n')
        await sleep(0.1)
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\nMsg2\nMsg3\n',
        'handler done'
    ]


def test_readall_partial(kernel, portno):
    done = Event()

    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        line = await s.readline()
        assert line == b'hello\n'
        data = await s.readall()
        assert data == b'world\n'
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'hello\nworld\n')
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())


def test_readall_timeout(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        try:
            data = await timeout_after(0.5, s.readall())
        except TaskTimeout as e:
            results.append(e.bytes_read)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\n')
        await sleep(1)
        await sock.send(b'Msg2\n')
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        'handler done'
    ]


def test_read_exactly(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        for n in range(3):
            results.append(await s.read_exactly(5))
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_read_exactly_incomplete(kernel, portno):
    done = Event()
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        try:
            await s.read_exactly(100)
        except EOFError as e:
            results.append(e.bytes_read)
        finally:
            await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results[0] ==  b'Msg1\nMsg2\nMsg3\n'

def test_read_exactly_timeout(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        try:
            data = await timeout_after(0.5, s.read_exactly(10))
            results.append(data)
        except TaskTimeout as e:
            results.append(e.bytes_read)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\n')
        await sleep(1)
        await sock.send(b'Msg2\n')
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        'handler done'
    ]



def test_readline(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        for n in range(3):
            results.append(await s.readline())
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_readlines(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        await client.send(b'OK')
        results.append('handler start')
        s = client.as_stream()
        results.extend(await s.readlines())
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_readlines_timeout(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        await client.send(b'OK')
        results.append('handler start')
        s = client.as_stream()
        try:
            await timeout_after(0.5, s.readlines())
        except TaskTimeout as e:
            results.extend(e.lines_read)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\n')
        await sleep(1)
        await sock.send(b'Msg3\n')
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        'handler done'
    ]


def test_writelines(kernel, portno):
    done = Event()
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        results.append(await s.readall())
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        s = sock.as_stream()
        await s.writelines([b'Msg1\n', b'Msg2\n', b'Msg3\n'])
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\nMsg2\nMsg3\n',
        'handler done'
    ]


def test_writelines_timeout(kernel, portno):
    done = Event()
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        await sleep(1)
        results.append(await s.readall())
        await done.set()

    def line_generator():
        n = 0
        while True:
            yield b'Msg%d\n' % n
            n += 1

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        s = sock.as_stream()
        try:
            await timeout_after(0.5, s.writelines(line_generator()))
        except TaskTimeout as e:
            results.append(e.bytes_written)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results[0] == len(results[1])

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="fails on windows")
def test_write_timeout(kernel, portno):
    done = Event()
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        await sleep(1)
        results.append(await s.readall())
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        s = sock.as_stream()
        try:
            msg = b'x'*10000000  # Must be big enough to fill buffers
            await timeout_after(0.5, s.write(msg))
        except TaskTimeout as e:
            results.append(e.bytes_written)
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results[0] == len(results[1])

def test_iterline(kernel, portno):
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        async for line in s:
            results.append(line)
        results.append('handler done')

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()
        await serv.cancel()

    async def main():
        async with TaskGroup() as g:
            serv = await g.spawn(tcp_server, '', portno, handler)
            await g.spawn(test_client, ('localhost', portno), serv)

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_double_recv(kernel, portno):
    done = Event()
    results = []

    async def bad_handler(client):
        results.append('bad handler')
        await sleep(0.1)
        try:
            await client.recv(1000)   # <- This needs to fail. Task already reading on the socket
            results.append('why am I here?')
        except ReadResourceBusy as e:
            results.append('good handler')

    async def handler(client, addr):
        results.append('handler start')
        await spawn(bad_handler, client, daemon=True)
        await client.send(b'OK')
        data = await client.recv(1000)
        results.append(data)
        results.append('handler done')
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sleep(1)
        await sock.send(b'Msg')
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        client = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await client.join()

    kernel.run(main())

    assert results == [
        'handler start',
        'bad handler',
        'good handler',
        b'Msg',
        'handler done'
        ]

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="fails on windows")
def test_sendall_cancel(kernel, portno):
    done = Event()
    start = Event()
    results = {}

    async def handler(client, addr):
        await start.wait()
        nrecv = 0
        while True:
            data = await client.recv(1000000)
            if not data:
                break
            nrecv += len(data)
        results['handler'] = nrecv
        await client.close()
        await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        try:
            await sock.sendall(b'x'*10000000)
        except CancelledError as e:
            results['sender'] = e.bytes_sent
        await sock.close()

    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        t = await spawn(test_client, ('localhost', portno), serv)
        await sleep(0.1)
        await t.cancel()
        await start.set()
        await serv.cancel()
        await done.wait()

    kernel.run(main())

    assert results['handler'] == results['sender']


def test_stream_bad_context(kernel, portno):
    done = Event()
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        try:
            with client.as_stream() as s:
                data = await s.readall()
        except AsyncOnlyError:
            results.append(True)
        finally:
            await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Hello\n')
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [ True ]

def test_stream_bad_iter(kernel, portno):
    done = Event()
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        try:
            async with client.as_stream() as s:
                for line in s:
                    pass
        except AsyncOnlyError:
            results.append(True)
        finally:
            await done.set()

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Hello\n')
        await sock.close()


    async def main():
        serv = await spawn(tcp_server, '', portno, handler)
        c = await spawn(test_client, ('localhost', portno), serv)
        await done.wait()
        await serv.cancel()
        await c.join()

    kernel.run(main())

    assert results == [ True ]

def test_io_waiting(kernel):
    async def handler(sock):
        result = await sock.accept()

    async def main():
        from curio.traps import _io_waiting

        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
        sock.bind(('',25000))
        sock.listen(1)
        async with sock:
            t1 = await spawn(handler, sock)
            await sleep(0.1)
            r, w = await _io_waiting(sock)
            assert t1 == r
            assert w == None
            await t1.cancel()

        r,w = await _io_waiting(0)
        assert (r, w) == (None, None)

    kernel.run(main())

def test_io_unregister(kernel):
    # This is purely a code coverage test
    async def reader(sock):
        from curio.traps import _read_wait
        await _read_wait(sock.fileno())

    async def main():
        from curio.traps import _write_wait
        sock = socket(AF_INET, SOCK_DGRAM)
        sock.bind(('', 26000))
        t = await spawn(reader(sock))
        await sleep(0.1)
        await _write_wait(sock.fileno())
        await t.cancel()
        await sock.close()
    kernel.run(main())
    assert True
