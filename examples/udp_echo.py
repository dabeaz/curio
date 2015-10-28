# udp_echo
#
# An example of a simple UDP echo server. 

import curio
from curio import network

async def main(addr):
    sock = await network.create_datagram_endpoint(addr, None)
    while True:
        data, addr = await sock.recvfrom(10000)
        print('Received from', addr, data)
        await sock.sendto(data, addr)

if __name__ == '__main__':
    kernel = curio.Kernel()
    kernel.run(main(('', 26000)))
