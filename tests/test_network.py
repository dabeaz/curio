# test_network.py
from os.path import dirname, join
import ssl
from functools import partial

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
        serv = await spawn(tcp_server, '', 25000, handler)
        await spawn(client, ('localhost', 25000), serv)

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
