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
            kernel.add_task(handler(client))
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

if __name__ == '__main__':
    unittest.main()
