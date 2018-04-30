# requestio.py
#
# And a hollow voice says "plugh"
#
# Well, well, well... it seems that you've wandered into a strange
# new world where things only get curioser and curioser.
#
# This is a highly experimental proof of concept example that shows
# how to make concurrent outgoing HTTP requests using the popular
# "requests" library, but under the control of cancellable tasks
# running in a Curio TaskGroup.  
#
# This example involves *NO* changes to the requests library, *NO*
# monkeypatching, or other kinds of conventional magic.  Instead,
# it defines a custom requests adapter object that creates connections
# using sockets designed for use with Curio's async thread feature.
# This adapter is then attached to a requests Session instance. 
#
# If you unravel the control flow of this and wrap your brain around
# how it works, you'll learn a lot.

# -- Standard library
from http.client import HTTPConnection

# -- Requests/third party
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3 import PoolManager, HTTPConnectionPool

# -- Curio
from curio import socket, run, TaskGroup, CancelledError
from curio.io import SyncSocket
from curio import async_thread, AWAIT

# All of the classes below are implementing a new requests adaptor. The
# whole point of this is to get requests to use a different kind of 
# socket object (curio.io.SyncSocket).  Sorry, it's a lot of plumbing.
# Maybe there's an easier way.

class RequestioAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block):
        self.poolmanager = RequestioPoolManager(num_pools=connections,
                                               maxsize=maxsize,
                                               block=block)

class RequestioPoolManager(PoolManager):
    def _new_pool(self, scheme, host, port, **kwargs):
        if scheme == 'http':
            return RequestioHTTPConnectionPool(host, port, **self.connection_pool_kw)

        return super(PoolManager, self)._new_pool(self, scheme, host, port, **kwargs)


class RequestioHTTPConnectionPool(HTTPConnectionPool):
    def _new_conn(self):
        self.num_connections += 1
        return RequestioHTTPConnection(host=self.host, port=self.port)

class RequestioHTTPConnection(HTTPConnection):
    def connect(self):
        """Connect to the host and port specified in __init__."""
        self.sock = AWAIT(socket.create_connection((self.host, self.port),
                                             self.timeout, self.source_address))

        orig_sock = self.sock._socket
        self.sock._socket = None

        # Replace the socket with a synchronous socket
        self.sock = SyncSocket(orig_sock)
        
        # Important!
        if self._tunnel_host:
            self._tunnel()

session = requests.Session()
session.mount('http://', RequestioAdapter())

# Example use
@async_thread
def fetch_url(url):
    try:
        print("Fetching", url)
        result = session.get(url)
        return result.json()
    except CancelledError as e:
        print("Cancelled", url)
        raise
    
async def main():
    urls = [ 
        'http://www.dabeaz.com/cgi-bin/saas.py?s=5',   # Sleep 5 seconds (cancelled)
        'http://www.dabeaz.com/cgi-bin/saas.py?s=10',  # Sleep 10 seconds (cancelled)
        'http://www.dabeaz.com/cgi-bin/fib.py?n=10',   # 10th Fibonacci number (succeeds)
        ] 

    results = []
    async with TaskGroup(wait=any) as g:
        for url in urls:
            await g.spawn(fetch_url, url)

    print(g.completed.result)

if __name__ == '__main__':
    run(main)

