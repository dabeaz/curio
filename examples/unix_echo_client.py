# udp_echo
#
# An example of a UDP echo client

import curio


async def main(addr):
    sock = await curio.open_unix_connection(addr)
    for i in range(1000):
        msg = ('Message %d' % i).encode('ascii')
        print(msg)
        await sock.send(msg)
        resp = await sock.recv(1000)
        assert msg == resp
    await sock.close()


if __name__ == '__main__':
    try:
        curio.run(main, '/tmp/curiounixecho')
    except KeyboardInterrupt:
        pass
