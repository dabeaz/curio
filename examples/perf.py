# perf.py
#
# Measure response rate of echo server

from socket import *
import time
from threading import Thread
import sys

if len(sys.argv) > 1:
    MSGSIZE = int(sys.argv[1])
else:
    MSGSIZE = 1

msg = b'x'*MSGSIZE

sock = socket(AF_INET, SOCK_STREAM)
sock.connect(('localhost', 25000))

N = 0
def monitor():
    global N
    while True:
        time.sleep(1)
        print(N, 'requests/sec')
        N = 0

Thread(target=monitor, daemon=True).start()

while True:
    sock.sendall(msg)
    nrecv = 0
    while nrecv < MSGSIZE:
        resp = sock.recv(MSGSIZE)
        if not resp:
            raise SystemExit()
        nrecv += len(resp)
    N += 1
