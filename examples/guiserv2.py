# guiserv2.py
#
# Another example of integrating Curio with the Tkinter
# event loop using UniversalQueue and threads.

import tkinter as tk
import threading
from curio import *

class EchoApp(object):
    def __init__(self):
        self.gui_ops = UniversalQueue(withfd=True)
        self.coro_ops = UniversalQueue()

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
                                           command=lambda: self.coro_ops.put(self.disconnect_all()))
        self.disconnect_button.pack()

        # Set up event handler for queued GUI updates
        self.root.createfilehandler(self.gui_ops, tk.READABLE, self.process_gui_ops)

    def incr_clients(self, delta=1):
        self.nclients += delta
        self.clients_label.configure(text='Number Clients %d' % self.nclients)

    def update_bytes(self):
        self.bytes_label.configure(text='Bytes received %d' % self.bytes_received)
        self.root.after(1000, self.update_bytes)

    def process_gui_ops(self, file, mask):
        while not self.gui_ops.empty():
            func, args = self.gui_ops.get()
            func(*args)

    async def echo_client(self, sock, address):
        await self.gui_ops.put((self.incr_clients, (1,)))
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
            self.client_tasks.remove(await current_task())
            await self.gui_ops.put((self.incr_clients, (-1,)))

    async def disconnect_all(self):
        for task in list(self.client_tasks):
            await task.cancel()

    async def main(self):
        serv = await spawn(tcp_server, '', 25000, self.echo_client)
        while True:
            coro = await self.coro_ops.get()
            await coro

    def run_forever(self):
        threading.Thread(target=run, args=(self.main,)).start()
        self.root.mainloop()

if __name__ == '__main__':
    app = EchoApp()
    app.run_forever()


