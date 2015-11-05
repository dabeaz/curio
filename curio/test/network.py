# curio/test/socket.py

import unittest
from ..import *
from ..socket import *

class TestSocketServer(unittest.TestCase):
    def test_tcp_echo_baserequest(self):
        kernel = get_kernel()
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

        serv = kernel.add_task(run_server('',25000,handler))
        kernel.add_task(client(('localhost', 25000), serv))
        kernel.run()

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

if __name__ == '__main__':
    unittest.main()
