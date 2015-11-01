# client.py
#
# Common client. Measure the response rate of the echo server
# Sends a large number of requests. Measures how long it takes.

from socket import *
import time
import sys

if len(sys.argv) > 1:
    MSGSIZE = int(sys.argv[1])
else:
    MSGSIZE = 1000

msg = b'x'*MSGSIZE

def run_test(n):
    sock = socket(AF_INET, SOCK_STREAM)
    sock.connect(('localhost', 25000))
    while n > 0:
        sock.sendall(msg)
        nrecv = 0
        while nrecv < MSGSIZE:
            resp = sock.recv(MSGSIZE)
            if not resp:
                raise SystemExit()
            nrecv += len(resp)
        n -= 1

NMESSAGES = 1000000
print('Sending', NMESSAGES, 'messages')
start = time.time()
run_test(NMESSAGES)
end = time.time()
duration = end-start
print(NMESSAGES,'in', duration)
print(NMESSAGES/duration, 'requests/sec')
