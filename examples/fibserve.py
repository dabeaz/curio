# An example of a server involving a CPU-intensive task.  We'll farm the 
# CPU-intensive work out to a separate process.

from curio import run, run_in_process, tcp_server

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

async def fib_handler(client, addr):
    print('Connection from', addr)
    rfile, wfile = client.make_streams()
    async with rfile, wfile:
        async for line in rfile:
            try:
                n = int(line)
                result = await run_in_process(fib, n)
                resp = str(result) + '\n'
                await wfile.write(resp.encode('ascii'))
            except ValueError:
                await wfile.write(b'Bad input\n')
    print('Connection closed')

if __name__ == '__main__':
    run(tcp_server('', 25000, fib_handler))



    
