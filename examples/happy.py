# happy.py
# An implementation of RFC 6555 (Happy Eyeballs).
# See: https://tools.ietf.org/html/rfc6555

if True:

    from curio import socket, TaskGroup, ignore_after, run
    import itertools

    async def open_tcp_stream(hostname, port, delay=0.3):
        # Get all of the possible targets for a given host/port
        targets = await socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        if not targets:
            raise OSError(f'nothing known about {hostname}:{port}')

        # Cluster the targets into unique address families (e.g., AF_INET, AF_INET6, etc.)
        # and make sure the first entries are from a different family.
        families = [ list(g) for _, g in itertools.groupby(targets, key=lambda t: t[0]) ]
        targets = [ fam.pop(0) for fam in families ]
        targets.extend(itertools.chain(*families))

        # Task group to manage a collection concurrent tasks. All die upon exit
        async with TaskGroup(wait=None) as group:

            # Attempt to make a connection request
            async def try_connect(sockargs, addr, errors):
                sock = socket.socket(*sockargs)
                try:
                    await sock.connect(addr)
                    return sock
                except Exception as e:
                    await sock.close()
                    errors.append(e)

            # List of accumulated errors to report in case of total failure
            errors = []

            # Walk the list of targets and try connections with a staggered delay
            for *sockargs, _, addr in targets:
                await group.spawn(try_connect, sockargs, addr, errors)
                sock = await ignore_after(delay, group.next_result)
                if sock:
                    return sock

            # Collect all of the remaining tasks looking for a good connection
            async for task in group:
                if task.result:
                    return task.result

            # It didn't work. Oh well.
            raise OSError(errors)

if True:
    async def main():
        result = await open_tcp_stream('www.python.org', 80)
        print(result)

if __name__ == '__main__':
    run(main)


    
    
    

    
    
    
