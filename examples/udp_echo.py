# udp_echo
#
# An example of a simple UDP echo server. 

import curio
from curio import socket

async def main(addr):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(addr)
    while True:
        data, addr = await sock.recvfrom(10000)
        print('Received from', addr, data)
        await sock.sendto(data, addr)

if __name__ == '__main__':
    curio.run(main(('', 26000)))
