from curio import run, spawn, TaskGroup, Queue, tcp_server, CancelledError
from curio.socket import *

import logging
log = logging.getLogger(__name__)

messages = Queue()
subscribers = set()

async def dispatcher():
    async for msg in messages:
        for q in subscribers:
            await q.put(msg)

async def publish(msg, local):
    log.info('%r published %r', local['address'], msg)
    await messages.put(msg)

async def outgoing(client_stream):
    queue = Queue()
    try:
        subscribers.add(queue)
        async for name, msg in queue:
            await client_stream.write(name + b':' + msg)
    finally:
        subscribers.discard(queue)

async def incoming(client_stream, name, local):
    try:
        async for line in client_stream:
            await publish((name, line), local)
    except CancelledError:
        await client_stream.write(b'SERVER IS GOING DOWN!\n')
        raise

async def chat_handler(client, addr):
    log.info('Connection from %r', addr) 
    local = { 'address': addr }
    async with client:
        client_stream = client.as_stream()
        await client_stream.write(b'Your name: ')
        name = (await client_stream.readline()).strip()
        await publish((name, b'joined\n'), local)

        async with TaskGroup(wait=any) as workers:
            await workers.spawn(outgoing, client_stream)
            await workers.spawn(incoming, client_stream, name, local)

        await publish((name, b'has gone away\n'), local)

    log.info('%r connection closed', addr)

async def chat_server(host, port):
    async with TaskGroup() as g:
        await g.spawn(dispatcher)
        await g.spawn(tcp_server, host, port, chat_handler)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run(chat_server('', 25000))
