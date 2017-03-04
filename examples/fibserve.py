# An example of a server involving a CPU-intensive task.  We'll farm the
# CPU-intensive work out to a separate process.

from curio import run, run_in_process, tcp_server


def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n - 1) + fib(n - 2)


async def fib_handler(client, addr):
    print('Connection from', addr)
    s = client.as_stream()
    async for line in s:
        try:
            n = int(line)
            result = await run_in_process(fib, n)
            resp = str(result) + '\n'
            await s.write(resp.encode('ascii'))
        except ValueError:
            await s.write(b'Bad input\n')
    print('Connection closed')
    await client.close()


if __name__ == '__main__':
    try:
        run(tcp_server, '', 25000, fib_handler)
    except KeyboardInterrupt:
        pass
