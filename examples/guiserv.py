# guiserv.py
#
# An example of connecting Curio and the Tkinter event loop
import tkinter as tk
from curio import *

class EchoApp(object):
    def __init__(self):
        # Pending coroutines
        self.pending = []

        # Main Tk window
        self.root = tk.Tk()

        # Number of clients connected label
        self.clients_label = tk.Label(text='')
        self.clients_label.pack()
        self.nclients = 0
        self.incr_clients(0)
        self.client_tasks = set()

        # Number of bytes received label
        self.bytes_received = 0
        self.bytes_label = tk.Label(text='')
        self.bytes_label.pack()
        self.update_bytes()

        # Disconnect all button
        self.disconnect_button = tk.Button(text='Disconnect all', 
                                           command=lambda: self.pending.append(self.disconnect_all()))
        self.disconnect_button.pack()

    def incr_clients(self, delta=1):
        self.nclients += delta
        self.clients_label.configure(text='Number Clients %d' % self.nclients)            

    def update_bytes(self):
        self.bytes_label.configure(text='Bytes received %d' % self.bytes_received)
        self.root.after(1000, self.update_bytes)

    async def echo_client(self, sock, address):
        self.incr_clients(1)
        self.client_tasks.add(await current_task())
        try:
            async with sock:
                while True:
                    data = await sock.recv(100000)
                    if not data:
                        break
                    self.bytes_received += len(data)
                    await sock.sendall(data)
        finally:
            self.incr_clients(-1)
            self.client_tasks.remove(await current_task())

    async def disconnect_all(self):
        for task in list(self.client_tasks):
            await task.cancel()

    async def main(self):
        serv = await spawn(tcp_server, '', 25000, self.echo_client)
        while True:
            self.root.update()
            for coro in self.pending:
                await coro
            self.pending = []
            await sleep(0.05)

if __name__ == '__main__':
    app = EchoApp()
    run(app.main)

