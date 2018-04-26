# happy.py
# An implementation of RFC 6555 (Happy Eyeballs)

from curio import socket, TaskGroup, ignore_after, run
import itertools

async def open_tcp_stream(hostname, port, delay=0.3):
    # Get all of the possible targets for a given host/port
    targets = await socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    if not targets:
        raise OSError(f'nothing known about {hostname}:{port}')

    # Group the targets into different address families (i.e., AF_INET, AF_INET6)
    families = { af: list(group)
                 for af, group in itertools.groupby(targets, key=lambda t: t[0]) }

    # Arrange the targets to interleave address families. Looks scary, but it's this
    # { k1: [a, b], k2: [x, y] } -> [ a, x, b, y ]
    targets = itertools.chain(*zip(*families.values()))

    # List of socket-related errors (if any)
    errors = []

    # Connection attempts are made to each target, but staggered with a delay.
    # Each connection attempt is launched in its own task.  The first successful
    # connection causes every other task to immediately cancel.
    async with TaskGroup(wait=any) as group:

        # Task that attempts to make a connection
        async def try_connect(sockargs, addr):
            try:
                sock = socket.socket(*sockargs)
                await sock.connect(addr)
                return sock
            except OSError as e:
                errors.append(e)
                await sock.close()

        # Task that tries all of the targets one after the other
        async def connector():
            for *sockargs, _, addr in targets:
                task = await group.spawn(try_connect, sockargs, sock, addr)
                async with ignore_after(delay):
                    await task.wait()

        await group.spawn(connector)

    # Get the connected socket from the first task that completed
    if group.completed:
        return group.completed.result
    else:
        raise OSError(errors)

async def main():
    result = await open_tcp_stream('www.python.org', 80)
    print(result)

if __name__ == '__main__':
    run(main)


    
    
    

    
    
    
