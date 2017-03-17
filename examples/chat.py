import signal
from curio import run, spawn, SignalQueue, TaskGroup, Queue, tcp_server, CancelledError, Local
from curio.socket import *

import logging
log = logging.getLogger(__name__)

messages = Queue()
subscribers = set()
local = Local()

async def dispatcher():
    async for msg in messages:
        for q in subscribers:
            await q.put(msg)

async def publish(msg):
    log.info('%r published %r', local.address, msg)
    await messages.put(msg)

async def outgoing(client_stream):
    queue = Queue()
    try:
        subscribers.add(queue)
        async for name, msg in queue:
            await client_stream.write(name + b':' + msg)
    finally:
        subscribers.discard(queue)

async def incoming(client_stream, name):
    try:
        async for line in client_stream:
            await publish((name, line))
    except CancelledError:
        await client_stream.write(b'SERVER IS GOING DOWN!\n')
        raise

async def chat_handler(client, addr):
    log.info('Connection from %r', addr) 
    local.address = addr
    async with client:
        client_stream = client.as_stream()
        await client_stream.write(b'Your name: ')
        name = (await client_stream.readline()).strip()
        await publish((name, b'joined\n'))

        async with TaskGroup(wait=any) as workers:
            await workers.spawn(outgoing, client_stream)
            await workers.spawn(incoming, client_stream, name)

        await publish((name, b'has gone away\n'))

    log.info('%r connection closed', local.address)

async def chat_server(host, port):
    async with TaskGroup() as g:
        await g.spawn(dispatcher)
        await g.spawn(tcp_server, host, port, chat_handler)

async def main(host, port):
    async with SignalQueue(signal.SIGHUP) as restart:
        while True:
            log.info('Starting the server')
            serv_task = await spawn(chat_server, host, port)
            await restart.get()
            log.info('Server shutting down')
            await serv_task.cancel()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run(main('', 25000))
