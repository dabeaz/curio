# A simple echo server with threads

from socket import *
from threading import Thread


def echo_server(addr):
    sock = socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(addr)
    sock.listen(5)
    while True:
        client, addr = sock.accept()
        Thread(target=echo_handler, args=(client, addr), daemon=True).start()


def echo_handler(client, addr):
    print('Connection from', addr)
    client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    with client:
        while True:
            data = client.recv(100000)
            if not data:
                break
            client.sendall(data)
    print('Connection closed')


if __name__ == '__main__':
    echo_server(('', 25000))
