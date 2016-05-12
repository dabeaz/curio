
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.internet import reactor, protocol, ssl
from twisted.internet.protocol import Factory

class Echo(protocol.Protocol):
    """This is just about the simplest possible protocol"""

    def connectionMade(self):
        self.transport.setTcpNoDelay(True)

    def dataReceived(self, data):
        "As soon as any data is received, write it back."
        self.transport.write(data)

KEYFILE = "ssl_test_rsa"    # Private key
CERTFILE = "ssl_test.crt"   # Certificate (self-signed)

def main():
    """This runs the protocol on port 25000"""
    factory = protocol.Factory()
    factory.protocol = Echo
    reactor.listenSSL(25000, factory,
                      ssl.DefaultOpenSSLContextFactory(KEYFILE, CERTFILE))
    reactor.run()

# this only runs if the module was *not* imported
if __name__ == '__main__':
    main()
