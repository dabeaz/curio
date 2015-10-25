# curio/test/socket.py

import unittest
from ..import *
from ..socketserver import *
from ..socket import *

class TestSocketServer(unittest.TestCase):
    def test_tcp_echo_baserequest(self):
        kernel = get_kernel()
        results = []

        class EchoHandler(BaseRequestHandler):
            async def handle(self):
                results.append('handler start')
                while True:
                    results.append('recv wait')
                    data = await self.request.recv(100)
                    if not data:
                        break
                    results.append(('handler', data))
                    await self.request.sendall(data)
                results.append('handler done')

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
            sock.close()

        serv = TCPServer(('',25000), EchoHandler)
        kernel.add_task(serv.handle_request())
        kernel.add_task(client(('localhost', 25000)))
        kernel.run()
        serv.server_close()

        self.assertEqual(results, [
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
                ])

    def test_tcp_echo_streamrequest(self):
        kernel = get_kernel()
        results = []

        class EchoHandler(StreamRequestHandler):
            async def handle(self):
                results.append('handler start')
                async for line in self.rfile:
                      results.append(('handler', line))
                      await self.wfile.write(line)
                      await self.wfile.flush()
                results.append('handler done')

        async def client(address):
            results.append('client start')
            sock = socket(AF_INET, SOCK_STREAM)
            await sock.connect(address)
            await sock.send(b'Msg1\n')
            await sleep(0.1)
            resp = await sock.recv(100)
            results.append(('client', resp))
            await sock.send(b'Msg2\n')
            await sleep(0.1)
            resp = await sock.recv(100)
            results.append(('client', resp))
            results.append('client close')
            sock.close()

        serv = TCPServer(('',25000), EchoHandler)
        kernel.add_task(serv.handle_request())
        kernel.add_task(client(('localhost', 25000)))
        kernel.run()
        serv.server_close()

        self.assertEqual(results, [
                'client start',
                'handler start',
                ('handler', b'Msg1\n'),
                ('client', b'Msg1\n'),
                ('handler', b'Msg2\n'),
                ('client', b'Msg2\n'),
                'client close',
                'handler done'
                ])

if __name__ == '__main__':
    unittest.main()
