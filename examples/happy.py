# happy.py
# An implementation of RFC 6555 (Happy Eyeballs).
# See: https://tools.ietf.org/html/rfc6555

from curio import socket, TaskGroup, ignore_after, run
import itertools

async def open_tcp_stream(hostname, port, delay=0.3):
    # Get all of the possible targets for a given host/port
    targets = await socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    if not targets:
        raise OSError(f'nothing known about {hostname}:{port}')

    # Cluster the targets into unique address families (e.g., AF_INET, AF_INET6, etc.)
    families = [ list(g) for _, g in itertools.groupby(sorted(targets), key=lambda t: t[0]) ]

    # Interleave the targets by address families
    #  [ [a, b], [x, y] ] -> [ a, x, b, y ]
    targets = itertools.chain(*zip(*families))

    # Task group to manage concurrent tasks. There can only be one winner.
    async with TaskGroup(wait=None) as group:

        # Function to attempt a connection request
        async def try_connect(sockargs, addr):
            sock = socket.socket(*sockargs)
            try:
                await sock.connect(addr)
                return sock
            except Exception:
                await sock.close()
                raise

        # List of accumulated errors to report in case of total failure
        errors = []

        # Walk the list of targets and try connections with a staggered delay
        for *sockargs, _, addr in targets:
            await group.spawn(try_connect, sockargs, addr)
            try:
                sock = await ignore_after(delay, group.next_result)
                if sock:
                    return sock     # Note: Returning cancels all remaining tasks
            except OSError as e:
                errors.append(e)

        raise OSError(errors)

async def main():
    result = await open_tcp_stream('www.python.org', 80)
    print(result)

if __name__ == '__main__':
    run(main)


    
    
    

    
    
    
