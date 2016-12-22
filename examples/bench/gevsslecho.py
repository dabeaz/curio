from gevent.server import StreamServer
from socket import IPPROTO_TCP, TCP_NODELAY

# this handler will be run for each incoming connection in a dedicated greenlet


def echo(socket, address):
    print('New connection from %s:%s' % address)
    socket.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    while True:
        data = socket.recv(102400)
        if not data:
            break
        socket.sendall(data)
    socket.close()

if __name__ == '__main__':
    KEYFILE = "ssl_test_rsa"
    CERTFILE = "ssl_test.crt"
    server = StreamServer(('0.0.0.0', 25000), echo, keyfile=KEYFILE, certfile=CERTFILE)
    server.serve_forever()
