from curio import *
from socket import *
import signal
import subprocess

async def monitor():
    async with SignalSet(signal.SIGUSR1, signal.SIGUSR2) as sigset:
        while True:
             try:
                  signo = await sigset.wait(timeout=30)
                  print('Caught signal', signo)
                  print('Ignoring signals for 30 seconds')
                  with sigset.ignore():
                        await sleep(30)
             except TimeoutError:
                  print('No signal')
             except CancelledError:
                  print('Cancelled')
                  return

async def subproc():
    p = Popen(['python3', 'slow.py'], stdout=subprocess.PIPE)
    while True:
        line = await p.stdout.readline()
        if not line:
            break
        print('subproc', line)
    await p.wait()
    print('Subproc done')

text = '''
This is some test code
More test
code
Some test input
'''

async def subproc():
    p = Popen(['wc'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    stdout, stderr = await p.communicate(text.encode('ascii'))
    print(':::stdout:::')
    print(stdout)
    print(':::stderr::')
    print(stderr)

async def subproc():
    p = Popen(['python3', 'slow.py'], stdout=subprocess.PIPE)
    stdout, _ = await p.communicate(timeout=10)
    await p.wait()
    print('Subproc done')
    print(stdout)

async def subproc():
    try:
         out = await run_subprocess(['python3', 'slow.py'], timeout=10)
         print(out.stdout)
         print('return code', out.returncode)
         print(out)
    except subprocess.CalledProcessError as e:
         print('Failed', e.returncode)
         print(e.stderr)
    print('Subproc done')

async def spinner(prefix, interval):
    n = 0
    while True:
        await sleep(interval)
        print(prefix, n)
        n += 1

async def main(address):
    task = await new_task(echo_server(address))
    await SignalSet(signal.SIGINT).wait()
    print('You hit control-C')
    await task.cancel()
    print('Shutdown complete')

async def echo_server(address):
    sock = Socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    with sock:
        while True:
             client, addr = await sock.accept()
             print('Connection from', addr)
             await new_task(echo_client(client))
             del client

async def echo_client(client):
    with client.makefile('rwb') as client_f:
        try:
             async for line in client_f:
                 await client_f.write(line)
        except CancelledError:
             await client_f.write(b'Server going down\n')
             
    print('Connection closed')

if __name__ == '__main__':
    import os
    print('pid', os.getpid())
    kernel = get_kernel()
    kernel.add_task(main(('',25000)))
    kernel.add_task(monitor())
    kernel.add_task(subproc())
    kernel.add_task(spinner('spin',1))
    kernel.run(pdb=True)



    
