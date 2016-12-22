# client.py
#
# Common client. Measure the response rate of the echo server

from socket import *
import time
from threading import Thread
import atexit
import sys

if len(sys.argv) > 1:
    MSGSIZE = int(sys.argv[1])
else:
    MSGSIZE = 1

msg = b'x' * MSGSIZE

sock = socket(AF_INET, SOCK_STREAM)
sock.connect(('localhost', 25000))
sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)

N = 0
results = []


def monitor():
    global N
    while True:
        time.sleep(1)
        print(N, 'requests/sec')
        results.append(N)
        N = 0

Thread(target=monitor, daemon=True).start()


def print_average():
    import statistics
    print('Average', statistics.mean(results), 'requests/sec')
atexit.register(print_average)

while True:
    sock.sendall(msg)
    nrecv = 0
    while nrecv < MSGSIZE:
        resp = sock.recv(MSGSIZE)
        if not resp:
            raise SystemExit()
        nrecv += len(resp)
    N += 1
