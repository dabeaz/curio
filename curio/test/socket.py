# curio/test/socket.py

import unittest
from socket import *
from ..import *

class TestSocket(unittest.TestCase):
    def test_tcp_echo(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_STREAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            sock.listen(5)
            results.append('accept wait')
            client, addr = await sock.accept()
            results.append('accept done')
            await new_task(handler(client))
            sock.close()

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
            client.close()

        async def client(address):
            results.append('client start')
            sock = Socket(AF_INET, SOCK_STREAM)
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
            sock.close()

        kernel.add_task(server(('',25000)))
        kernel.add_task(client(('localhost', 25000)))
        kernel.run()

        self.assertEqual(results, [
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
                ])

    def test_udp_echo(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_DGRAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            results.append('recvfrom wait')
            data, addr = await sock.recvfrom(8192)
            results.append(('server', data))
            await sock.sendto(data, addr)
            sock.close()
            results.append('server close')

        async def client(address):
            results.append('client start')
            sock = Socket(AF_INET, SOCK_DGRAM)
            results.append('client send')
            await sock.sendto(b'Msg1', address)
            data, addr = await sock.recvfrom(8192)
            results.append(('client', data))
            sock.close()
            results.append('client close')
            sock.close()

        kernel.add_task(server(('',25000)))
        kernel.add_task(client(('localhost', 25000)))
        kernel.run()

        self.assertEqual(results, [
                'recvfrom wait',
                'client start',
                'client send',
                ('server', b'Msg1'),
                'server close',
                ('client', b'Msg1'),
                'client close'
                ])

    def test_accept_timeout(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_STREAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            sock.listen(1)
            sock.settimeout(0.5)
            results.append('accept wait')
            try:
                client, addr = await sock.accept()
                results.append('not here')
            except TimeoutError:
                results.append('accept timeout')
            sock.close()

        kernel.add_task(server(('',25000)))
        kernel.run()

        self.assertEqual(results, [
                'accept wait',
                'accept timeout'
                ])

    def test_accept_cancel(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_STREAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            sock.listen(1)
            results.append('accept wait')
            try:
                client, addr = await sock.accept()
                results.append('not here')
            except CancelledError:
                results.append('accept cancel')
            sock.close()

        async def canceller():
             task = await new_task(server(('',25000)))
             await sleep(0.5)
             await task.cancel()

        kernel.add_task(canceller())
        kernel.run()
        self.assertEqual(results, [
                'accept wait',
                'accept cancel'
                ])

    def test_recv_timeout(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_STREAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            sock.listen(1)
            results.append('accept wait')
            client, addr = await sock.accept()
            results.append('recv wait')
            client.settimeout(0.5)
            try:
                data = await client.recv(8192)
                results.append('not here')
            except TimeoutError:
                results.append('recv timeout')
            client.close()
            sock.close()

        async def canceller():
             task = await new_task(server(('',25000)))
             sock = Socket(AF_INET, SOCK_STREAM)
             results.append('client connect')
             await sock.connect(('localhost', 25000))
             await sleep(1.0)
             sock.close()
             results.append('client done')

        kernel.add_task(canceller())
        kernel.run()

        self.assertEqual(results, [
                'accept wait',
                'client connect',
                'recv wait',
                'recv timeout',
                'client done'
                ])


    def test_recv_cancel(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_STREAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            sock.listen(1)
            results.append('accept wait')
            client, addr = await sock.accept()
            results.append('recv wait')
            try:
                data = await client.recv(8192)
                results.append('not here')
            except CancelledError:
                results.append('recv cancel')
            client.close()
            sock.close()

        async def canceller():
             task = await new_task(server(('',25000)))
             sock = Socket(AF_INET, SOCK_STREAM)
             results.append('client connect')
             await sock.connect(('localhost', 25000))
             await sleep(1.0)
             await task.cancel()
             sock.close()
             results.append('client done')

        kernel.add_task(canceller())
        kernel.run()

        self.assertEqual(results, [
                'accept wait',
                'client connect',
                'recv wait',
                'recv cancel',
                'client done'
                ])

    def test_recvfrom_timeout(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_DGRAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            sock.settimeout(0.5)
            results.append('recvfrom wait')
            try:
                await sock.recvfrom(8192)
                results.append('not here')
            except TimeoutError:
                results.append('recvfrom timeout')
            sock.close()

        async def canceller():
             await new_task(server(('',25000)))
             await sleep(1.0)
             results.append('client done')

        kernel.add_task(canceller())
        kernel.run()

        self.assertEqual(results, [
                'recvfrom wait',
                'recvfrom timeout',
                'client done'
                ])


    def test_recvfrom_cancel(self):
        kernel = get_kernel()
        results = []
        async def server(address):
            sock = Socket(AF_INET, SOCK_DGRAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            sock.bind(address)
            results.append('recvfrom wait')
            try:
                await sock.recvfrom(8192)
                results.append('not here')
            except CancelledError:
                results.append('recvfrom cancel')
            sock.close()

        async def canceller():
             task = await new_task(server(('',25000)))
             await sleep(1.0)
             await task.cancel()
             results.append('client done')

        kernel.add_task(canceller())
        kernel.run()

        self.assertEqual(results, [
                'recvfrom wait',
                'recvfrom cancel',
                'client done'
                ])


if __name__ == '__main__':
    unittest.main()
