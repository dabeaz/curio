"""A Curio websocket server.

pip install wsproto before running this.

"""
from curio import Queue, run, spawn, wait
from curio.socket import IPPROTO_TCP, TCP_NODELAY
from wsproto.connection import WSConnection, SERVER
from wsproto.events import (ConnectionClosed, ConnectionRequested, TextReceived,
                            BytesReceived)

DATA_TYPES = (TextReceived, BytesReceived)


async def ws_adapter(in_q, out_q, client, _):
    """A simple, queue-based Curio-Sans-IO websocket bridge."""
    client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    wsconn = WSConnection(SERVER)
    closed = False

    while not closed:
        wstask = await spawn(client.recv(65535))
        outqtask = await spawn(out_q.get())
        async with wait((wstask, outqtask)) as w:
            task = await w.next_done()
            result = await task.join()

        if task is wstask:
            wsconn.receive_bytes(result)

            for event in wsconn.events():
                cl = event.__class__
                if cl in DATA_TYPES:
                    await in_q.put(event.data)
                elif cl is ConnectionRequested:
                    # Auto accept. Maybe consult the handler?
                    wsconn.accept(event)
                elif cl is ConnectionClosed:
                    # The client has closed the connection.
                    await in_q.put(None)
                    closed = True
                else:
                    print(event)
            await client.sendall(wsconn.bytes_to_send())
        else:
            # We got something from the out queue.
            if result is None:
                # Terminate the connection.
                print("Closing the connection.")
                wsconn.close()
                closed = True
            else:
                wsconn.send_data(result)
            payload = wsconn.bytes_to_send()
            await client.sendall(payload)
    print("Bridge done.")


async def ws_echo_server(in_queue, out_queue):
    """Just echo websocket messages, reversed. Echo 3 times, then close."""
    for _ in range(3):
        msg = await in_queue.get()
        if msg is None:
            # The ws connection was closed.
            break
        await out_queue.put(msg[::-1])
    print("Handler done.")


def serve_ws(handler):
    """Start processing web socket messages using the given handler."""
    async def run_ws(client, addr):
        in_q, out_q = Queue(), Queue()
        ws_task = await spawn(ws_adapter(in_q, out_q, client, addr))
        await handler(in_q, out_q)
        await out_q.put(None)
        await ws_task.join()  # Wait until it's done.
        # Curio will close the socket for us after we drop off here.
        print("Master task done.")

    return run_ws


if __name__ == '__main__':
    from curio import tcp_server
    port = 5000
    print(f'Listening on port {port}.')
    run(tcp_server('', port, serve_ws(ws_echo_server)))
