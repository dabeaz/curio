# test_network.py
from os.path import dirname, join
import sys
import os
import ssl
from functools import partial
import pytest

from curio import *
from curio import network
from curio import ssl as curiossl
from curio.socket import *

def test_tcp_echo(kernel):
    results = []

    async def handler(client, addr):
        results.append('handler start')
        while True:
            results.append('recv wait')
            data = await client.recv(100)
            if not data:
                break
            results.append(('handler', data))
            await client.sendall(data)
        results.append('handler done')

    async def client(address, serv):
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
        await serv.cancel()

    async def main():
        async with TaskGroup() as g:
            serv = await g.spawn(tcp_server, '', 25000, handler)
            await g.spawn(client, ('localhost', 25000), serv)

    kernel.run(main())

    assert results == [
        'client start',
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

if not sys.platform.startswith('win'): 
    def test_unix_echo(kernel):
        results = []

        async def handler(client, addr):
            results.append('handler start')
            while True:
                results.append('recv wait')
                data = await client.recv(100)
                if not data:
                    break
                results.append(('handler', data))
                await client.sendall(data)
            results.append('handler done')

        async def client(address, serv):
            results.append('client start')
            sock = await network.open_unix_connection(address)
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
            await serv.cancel()

        async def main():
            try:
                os.remove('/tmp/curionet')
            except OSError:
                pass
            async with TaskGroup() as g:
                serv = await g.spawn(unix_server, '/tmp/curionet', handler)
                await g.spawn(client, '/tmp/curionet', serv)

        kernel.run(main())

        assert results == [
            'client start',
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


def test_ssl_server(kernel):

    async def client(host, port, context):
        sock = await network.open_connection(host, port, ssl=context, server_hostname=host)
        await sock.sendall(b'Hello, world!')
        resp = await sock.recv(4096)
        return resp

    async def handler(client_sock, addr):
        data = await client_sock.recv(1000)
        assert data == b'Hello, world!'
        await client_sock.send(b'Back atcha: ' + data)

    async def main():
        # It might be desirable to move these out of the examples
        # directory, as this test are now relying on them being around
        file_path = join(dirname(dirname(__file__)), 'examples')
        cert_file = join(file_path, 'ssl_test.crt')
        key_file = join(file_path, 'ssl_test_rsa')

        server_context = curiossl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        server_context.load_cert_chain(certfile=cert_file, keyfile=key_file)

        stdlib_client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        curio_client_context = curiossl.create_default_context(ssl.Purpose.SERVER_AUTH)

        server_task = await spawn(partial(network.tcp_server, '', 10000, handler, ssl=server_context))
        await sleep(0.1)

        for test_context in (curio_client_context, stdlib_client_context):
            test_context.check_hostname = False
            test_context.verify_mode = ssl.CERT_NONE
            resp = await client('localhost', 10000, test_context)
            assert resp == b'Back atcha: Hello, world!'

        await server_task.cancel()

    kernel.run(main())

if not sys.platform.startswith('win'): 
    def test_unix_ssl_server(kernel):
        async def client(address, context):
            sock = await network.open_unix_connection(address, ssl=context)
            await sock.sendall(b'Hello, world!')
            resp = await sock.recv(4096)
            return resp

        async def handler(client_sock, addr):
            data = await client_sock.recv(1000)
            assert data == b'Hello, world!'
            await client_sock.send(b'Back atcha: ' + data)

        async def main():
            # It might be desirable to move these out of the examples
            # directory, as this test are now relying on them being around
            file_path = join(dirname(dirname(__file__)), 'examples')
            cert_file = join(file_path, 'ssl_test.crt')
            key_file = join(file_path, 'ssl_test_rsa')

            server_context = curiossl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            server_context.load_cert_chain(certfile=cert_file, keyfile=key_file)

            stdlib_client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            curio_client_context = curiossl.create_default_context(ssl.Purpose.SERVER_AUTH)

            try:
                os.remove('/tmp/curionet')
            except OSError:
                pass
            server_task = await spawn(partial(network.unix_server, '/tmp/curionet', handler, ssl=server_context))
            await sleep(0.1)

            for test_context in (curio_client_context, stdlib_client_context):
                test_context.check_hostname = False
                test_context.verify_mode = ssl.CERT_NONE
                resp = await client('/tmp/curionet', test_context)
                assert resp == b'Back atcha: Hello, world!'

            await server_task.cancel()

        kernel.run(main())


def test_ssl_wrapping(kernel):

    async def client(host, port, context):
        sock = await network.open_connection(host, port, ssl=context, server_hostname=host)
        await sock.sendall(b'Hello, world!')
        resp = await sock.recv(4096)
        return resp

    async def handler(client_sock, addr):
        data = await client_sock.recv(1000)
        assert data == b'Hello, world!'
        await client_sock.send(b'Back atcha: ' + data)

    def server(host, port, context):
        sock = socket(AF_INET, SOCK_STREAM)
        try:
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind((host, port))
            sock.listen(5)
            return network.run_server(sock, handler, context)
        except Exception:
            sock._socket.close()
            raise
        
    async def main():
        # It might be desirable to move these out of the examples
        # directory, as this test are now relying on them being around
        file_path = join(dirname(dirname(__file__)), 'examples')
        cert_file = join(file_path, 'ssl_test.crt')
        key_file = join(file_path, 'ssl_test_rsa')

        server_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        server_context.load_cert_chain(certfile=cert_file, keyfile=key_file)

        stdlib_client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        curio_client_context = curiossl.create_default_context(ssl.Purpose.SERVER_AUTH)

        server_task = await spawn(server, 'localhost', 10000, server_context)

        for test_context in (curio_client_context, stdlib_client_context):
            test_context.check_hostname = False
            test_context.verify_mode = ssl.CERT_NONE
            resp = await client('localhost', 10000, test_context)
            assert resp == b'Back atcha: Hello, world!'

        await server_task.cancel()

    kernel.run(main())

def test_ssl_outgoing(kernel):
    async def main():
        c = await network.open_connection('google.com', 443, ssl=True, server_hostname='google.com')
        await c.close()

        c = await network.open_connection('google.com', 443, ssl=True)
        await c.close()

        c = await network.open_connection('google.com', 443, ssl=True, alpn_protocols=['h2'])
        await c.close()


    kernel.run(main)

def test_ssl_manual_wrapping(kernel):

    async def client(host, port, context):
        sock = socket(AF_INET, SOCK_STREAM)
        await sock.connect((host, port))
        ssl_sock = await context.wrap_socket(sock, server_hostname=host)
        await ssl_sock.sendall(b'Hello, world!')
        resp = await ssl_sock.recv(4096)
        return resp

    async def handler(client_sock, addr):
        data = await client_sock.recv(1000)
        assert data == b'Hello, world!'
        await client_sock.send(b'Back atcha: ' + data)

    def server(host, port, context):
        sock = socket(AF_INET, SOCK_STREAM)
        try:
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind((host, port))
            sock.listen(5)
            return network.run_server(sock, handler, context)
        except Exception:
            sock._socket.close()
            raise
        
    async def main():
        # It might be desirable to move these out of the examples
        # directory, as this test are now relying on them being around
        file_path = join(dirname(dirname(__file__)), 'examples')
        cert_file = join(file_path, 'ssl_test.crt')
        key_file = join(file_path, 'ssl_test_rsa')

        server_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        server_context.load_cert_chain(certfile=cert_file, keyfile=key_file)

        curio_client_context = curiossl.create_default_context(ssl.Purpose.SERVER_AUTH)
        server_task = await spawn(server, 'localhost', 10000, server_context)

        curio_client_context.check_hostname = False
        curio_client_context.verify_mode = ssl.CERT_NONE
        resp = await client('localhost', 10000, curio_client_context)
        assert resp == b'Back atcha: Hello, world!'

        await server_task.cancel()

    kernel.run(main())

def test_errors(kernel):
    async def main():
        with pytest.raises(ValueError):
            c = await network.open_connection('google.com', 443, server_hostname='google.com')
            await c.close()

        with pytest.raises(Exception):
            c = await network.open_connection('google.com', 443, ssl=True, server_hostname='yahoo.com')
            await c.close()

        with pytest.raises(ValueError):
            await network.tcp_server('localhost', 25000, None, ssl=True)


        if not sys.platform.startswith('win'):
            with pytest.raises(OSError):
                await network.tcp_server('localhost', 0, None)

            with pytest.raises(OSError):
                await network.unix_server('/tmp', None)

            with pytest.raises(ValueError):
                c = await network.open_unix_connection('/tmp/curionet', server_hostname='google.com')
                await c.close()

    kernel.run(main)

