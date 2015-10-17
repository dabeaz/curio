import curio
from socket import *
from fib import fib
from concurrent.futures import ProcessPoolExecutor
import subprocess

pool = ProcessPoolExecutor()

async def fib_server(address):
    sock = curio.Socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    try:
        print('Waiting for connection')
        while True:
            client, addr = await sock.accept()
            print('Connection from', addr)
            kernel.add_task(fib_client(client))
    except curio.CancelledError:
        print('Server cancelled')
        
async def fib_client(client):
    with client:
        while True:
            data = await client.recv(1000)
            if not data:
                break
            n = int(data)
            result = await kernel.run_in_executor(pool, fib, n)
            data = str(result).encode('ascii') + b'\n'
            await client.send(data)
    print('Connection closed')

async def udp_echo(address):
    sock = curio.Socket(AF_INET, SOCK_DGRAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
    sock.bind(address)
    
    while True:
        msg, addr = await sock.recvfrom(8192)
        print('Message from', addr)
        await sock.sendto(msg, addr)

async def spinner(prefix, interval):
    n = 0
    while True:
        await curio.sleep(interval)
        print(prefix, n)
        n += 1

async def subproc():
    p = subprocess.Popen(['python3', 'slow.py'], stdout=subprocess.PIPE)
    f = curio.File(p.stdout)
    while True:
        line = await f.readline()
        if not line:
            break
        print('subproc', line)
    print('Subproc done')

# Test socketserver

from curio.socketserver import TCPServer, UDPServer, BaseRequestHandler, StreamRequestHandler

class EchoHandler(BaseRequestHandler):
    async def handle(self):
        print('Echo connection from', self.client_address)
        while True:
            data = await self.request.recv(1000)
            if not data:
                break
            await self.request.sendall(b'Got:' + data)
        print('Client done')

server = TCPServer(('', 27000), EchoHandler)

class EchoUDPHandler(BaseRequestHandler):
    async def handle(self):
        print('Echo connection from', self.client_address)
        data, sock = self.request
        await sock.sendto(b'Got:' + data, self.client_address)

udpserver = UDPServer(('', 28000), EchoUDPHandler)

class EchoStreamHandler(StreamRequestHandler):
    async def handle(self):
          print('Echo connection from', self.client_address)
          while True:
              line = await self.rfile.readline()
              if not line:
                  break
              await self.wfile.write(b'Line:' + line)
          print('Client done')

eserver = TCPServer(('', 29000), EchoStreamHandler)

async def event_setter(evt, seconds):
     await curio.sleep(seconds)
     print('About to set', evt)
     evt.set()
     print('Done setting', evt)

async def event_waiter(evt):
     await evt.wait()
     print('Event waiter done', evt)

async def task_locked(n, lck):
     while n > 0:
          await lck.acquire()
          print('Lock acquired')
          await curio.sleep(4)
          lck.release()
          n -= 1

async def task_locked_with(n, lck):
     while n > 0:
         async with lck:
             print('With lock acquired')
             await curio.sleep(4)
         n -= 1


class Counter(object):
    def __init__(self):
        self.n = 0
        self.cond = curio.Condition(curio.Semaphore())

async def count_monitor(c):
     while True:
         async with c.cond:
              print('Monitor: n=', c.n)
              await c.cond.wait()

async def count_update(c):
      while True:
          await curio.sleep(5)
          print('Count update', c.cond._lock)
          async with c.cond:
              print('Updating count')
              c.n += 1
              c.cond.notify()

async def queue_getter(q):
    while True:
         item = await q.get()
         print('Got queue:', item)

async def queue_putter(q):
    n = 0
    while True:
         await q.put(n)
         n += 1
         await curio.sleep(4)


async def queue_test(kernel):
    print('Queue Test')
    q = curio.Queue()
    async def queue_worker():
          while True:
               item = await q.get()
               await curio.sleep(4)
               print('Worker processed', item)
               q.task_done()
          
    kernel.add_task(queue_worker())
    for n in range(10):
        await q.put(n)

    await q.join()
    print('Queue Test Worker finished')

def cancel_test1(kernel):
    async def task_a():
        try:
            print('Sleeping')
            await curio.sleep(1000)
        except curio.CancelledError as e:
            print('Cancelled')

    async def task_b():
        tid = kernel.add_task(task_a())
        print('Created task', tid)
        await curio.sleep(10)
        print('About to cancel')
        kernel.cancel_task(tid)
        print('Done with cancel')

    kernel.add_task(task_b())

def cancel_test2(kernel):
    async def task_b():
        tid = kernel.add_task(fib_server(('', 25000)))
        await curio.sleep(10)
        print('About to cancel')
        kernel.cancel_task(tid)
        print('Done with cancel')

    kernel.add_task(task_b())

def cancel_test3(kernel):
    async def task_a(q):
        try:
            print('Waiting for an item')
            item = await q.get()
        except curio.CancelledError:
            print('Waiting cancelled')
            await curio.sleep(2)
            print('Waiting really cancelled')
    
    async def task_b():
        q = curio.Queue()
        tid = kernel.add_task(task_a(q))
        print('Created task', tid)
        await curio.sleep(10)
        print('About to cancel')
        kernel.cancel_task(tid)
        print('Done with cancel')

    kernel.add_task(task_b())

def cancel_test4(kernel):
    async def task_a(lck):
        try:
            async with lck:
                 print('Holding a lock. Ho hum')
                 await curio.sleep(1000)
        except curio.CancelledError:
            print('Cancelled!')
            print('Wait? Am I still holding the lock or not?')
    
    async def task_b():
        lck = curio.Lock()
        tid = kernel.add_task(task_a(lck))
        print('Created task', tid)
        await curio.sleep(10)
        print('About to cancel')
        kernel.cancel_task(tid)
        async with lck:
            print('Hey, I got the lock. Good')
        print('Done with cancel')

    kernel.add_task(task_b())


def cancel_test5(kernel):
    async def task_a(lck):
        try:
            print('Trying to get the lock')
            async with lck:
                 print('Hey. I got it. What?')
        except curio.CancelledError:
            print('Cancelled!')
            print('Sure hope I didn\'t get that lock')
    
    async def task_b():
        lck = curio.Lock()
        async with lck:
            tid = kernel.add_task(task_a(lck))
            print('Created task', tid)
            await curio.sleep(10)
            print('About to cancel')
            kernel.cancel_task(tid)
            print('Done with cancel')

    kernel.add_task(task_b())

def timeout_test1(kernel):
    async def task_a():
         sock = curio.Socket(AF_INET, SOCK_DGRAM)
         sock.bind(('', 30000))
         sock.settimeout(15)
         print('Socket created:', sock)
         while True:
             try:
                 msg = await sock.recvfrom(8192)
                 print('Got:', msg)
             except curio.TimeoutError:
                 print('Timeout. No message')

    kernel.add_task(task_a())

def timeout_test2(kernel):
    async def task_a(q):
        while True:
            try:
                print('Waiting for an item')
                item = await q.get(timeout=15)
            except curio.TimeoutError:
                print('Timed out. Trying again')
            except curio.CancelledError:
                print('Waiting cancelled')
                return
    
    async def task_b():
        q = curio.Queue()
        tid = kernel.add_task(task_a(q))
        print('Created task', tid)
        await curio.sleep(60)
        print('About to cancel')
        kernel.cancel_task(tid)
        print('Done with cancel')

    kernel.add_task(task_b())

def timeout_test3(kernel):
    async def task_a(lck):
        try:
            await lck.acquire(timeout=10)
            print('Got the lock')
            lck.release()
        except curio.TimeoutError:
            print('Lock timeout. Oh well. Goodbye')
    
    async def task_b():
        lck = curio.Lock()
        tid = kernel.add_task(task_a(lck))
        print('Created task', tid)
        async with lck:
            await curio.sleep(15)
        print('Did it ever get the lock?')

    kernel.add_task(task_b())

def timeout_test4(kernel):
    async def task_a(lck):
        try:
            await curio.alarm(10)
            print('Trying to get the lock')
            async with lck:
                print('Got the lock')
        except curio.TimeoutError:
            print('Lock timeout. Oh well. Goodbye')
    
    async def task_b():
        lck = curio.Lock()
        async with lck:
            tid = kernel.add_task(task_a(lck))
            print('Created task', tid)
            await curio.sleep(15)
        print('Did it ever get the lock?')

    kernel.add_task(task_b())


kernel = curio.get_kernel()
kernel.add_task(fib_server(('',25000)))


# timeout_test4(kernel)

if True:
    kernel.add_task(queue_test(kernel))

    q = curio.Queue()
    kernel.add_task(queue_putter(q))
    kernel.add_task(queue_getter(q))

    cnt = Counter()
    kernel.add_task(count_monitor(cnt))
    kernel.add_task(count_update(cnt))

    evt = curio.Event()
    kernel.add_task(event_waiter(evt))
    kernel.add_task(event_waiter(evt))
    kernel.add_task(event_setter(evt, 30))

    lck = curio.Semaphore(2)
    kernel.add_task(task_locked(5, lck))
    kernel.add_task(task_locked(5, lck))
    kernel.add_task(task_locked_with(5, lck))
    kernel.add_task(task_locked_with(5, lck))



#kernel.add_task(server.serve_forever())
#kernel.add_task(eserver.serve_forever())
#kernel.add_task(udpserver.serve_forever())

#kernel.add_task(spinner('spin1', 5))
#kernel.add_task(spinner('spin2', 1))
#kernel.add_task(udp_echo(('',26000)))
#kernel.add_task(subproc())
kernel.run(detached=True)

