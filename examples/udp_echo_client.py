# udp_echo
#
# An example of a UDP echo client

import curio
from curio import network

async def main(host, port):
    sock = await network.create_datagram_endpoint(None, (host, port))
    for i in range(1000):
        msg = ('Message %d' % i).encode('ascii')
        print(msg)
        await sock.send(msg)
        resp = await sock.recv(1000)
        assert msg == resp
    await sock.close()

if __name__ == '__main__':
    kernel = curio.Kernel()
    kernel.run(main('localhost', 26000))
