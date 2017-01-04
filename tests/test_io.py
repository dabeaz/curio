# test_io.py

from curio import *
from curio.socket import *
import io
import socket as std_socket


def test_socket_blocking(kernel):
    '''
    Test of exposing a socket in blocking mode
    '''
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

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Message')
        data = await sock.recv(8192)
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        ('client', b'Message'),
        'handler done'
    ]


def test_socketstream_blocking(kernel):
    '''
    Test of exposing a socket stream in blocking mode
    '''
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

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Message')
        data = await sock.recv(8192)
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        ('client', b'Message'),
        'handler done'
    ]


def test_filestream_blocking(kernel):
    '''
    Test of exposing a socket in blocking mode
    '''
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

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Message')
        data = await sock.recv(8192)
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        ('client', b'Message'),
        'handler done'
    ]


def test_readall(kernel):
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        data = await s.readall()
        results.append(data)
        results.append('handler done')

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
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\nMsg2\nMsg3\n',
        'handler done'
    ]


def test_readall_timeout(kernel):
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

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\n')
        await sleep(1)
        await sock.send(b'Msg2\n')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        'handler done'
    ]


def test_read_exactly(kernel):
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        for n in range(3):
            results.append(await s.read_exactly(5))
        results.append('handler done')

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_read_exactly_timeout(kernel):
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

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\n')
        await sleep(1)
        await sock.send(b'Msg2\n')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        'handler done'
    ]



def test_readline(kernel):
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        for n in range(3):
            results.append(await s.readline())
        results.append('handler done')

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_readlines(kernel):
    results = []

    async def handler(client, addr):
        await client.send(b'OK')
        results.append('handler start')
        s = client.as_stream()
        results.extend(await s.readlines())
        results.append('handler done')

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\nMsg3\n')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_readlines_timeout(kernel):
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

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sock.send(b'Msg1\nMsg2\n')
        await sleep(1)
        await sock.send(b'Msg3\n')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        'handler done'
    ]


def test_writelines(kernel):
    results = []

    async def handler(client, addr):
        results.append('handler start')
        await client.send(b'OK')
        s = client.as_stream()
        results.append(await s.readall())
        results.append('handler done')

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        s = sock.as_stream()
        await s.writelines([b'Msg1\n', b'Msg2\n', b'Msg3\n'])
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\nMsg2\nMsg3\n',
        'handler done'
    ]


def test_writelines_timeout(kernel):
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        await sleep(1)
        results.append(await s.readall())

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
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results[0] == len(results[1])


def test_write_timeout(kernel):
    results = []
    async def handler(client, addr):
        await client.send(b'OK')
        s = client.as_stream()
        await sleep(1)
        results.append(await s.readall())

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
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results[0] == len(results[1])

def test_iterline(kernel):
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
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        b'Msg1\n',
        b'Msg2\n',
        b'Msg3\n',
        'handler done'
    ]


def test_double_recv(kernel):
    results = []

    async def bad_handler(client):
        results.append('bad handler')
        await sleep(0.1)
        try:
            await client.recv(1000)   # <- This needs to fail. Task already reading on the socket
            results.append('why am I here?')
        except CurioError as e:
            results.append('good handler')

    async def handler(client, addr):
        results.append('handler start')
        await spawn(bad_handler(client))
        await client.send(b'OK')
        data = await client.recv(1000)
        results.append(data)
        results.append('handler done')

    async def test_client(address, serv):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect(address)
        await sock.recv(8)
        await sleep(1)
        await sock.send(b'Msg')
        await sock.close()
        await serv.cancel()

    async def main():
        serv = await spawn(tcp_server('', 25000, handler))
        await spawn(test_client(('localhost', 25000), serv))

    kernel.run(main())

    assert results == [
        'handler start',
        'bad handler',
        'good handler',
        b'Msg',
        'handler done'
        ]
