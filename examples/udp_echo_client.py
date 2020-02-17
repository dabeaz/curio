# udp_echo
#
# An example of a UDP echo client

import curio
from curio import socket


async def main(addr):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    await sock.connect(addr)
    for i in range(1000):
        msg = ('Message %d' % i).encode('ascii')
        print(msg)
        await sock.send(msg)
        resp = await sock.recv(1000)
        assert msg == resp
    await sock.close()


if __name__ == '__main__':
    curio.run(main, ('localhost', 26000))
