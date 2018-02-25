# dualserve.py
#
# An example of a server implementation that works both in Curio and
# as a normal threaded application

import threading
from curio import run, spawn_thread, async_thread, AWAIT

# This is a normal synchronous function.  It is used in both synchronous
# and asynchronous code.

def echo_handler(client, addr):
    print('Connection from', addr)
    with client:
        while True:
            data = AWAIT(client.recv, 100000)
            if not data:
                break
            AWAIT(client.sendall, b'Got:' + data)
    print('Connection closed')

# A Traditional threaded server
def threaded_echo_server(addr):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.bind(addr)
    sock.listen(5)
    print('Threaded server running on:', addr)
    while True:
        client, addr = sock.accept()
        threading.Thread(target=echo_handler, args=(client, addr), daemon=True).start()

# An async server
async def async_echo_server(addr):
    import curio.socket as socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.bind(addr)
    sock.listen(5)
    print('Async server running on:', addr)
    while True:
        client, addr = await sock.accept()
        await spawn_thread(echo_handler, client, addr, daemon=True)

if __name__ == '__main__':
    threading.Thread(target=threaded_echo_server, args=(('',25000),)).start()
    run(async_echo_server, ('',26000))



