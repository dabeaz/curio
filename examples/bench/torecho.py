
from tornado.ioloop import IOLoop
from tornado.tcpserver import TCPServer


class EchoServer(TCPServer):

    def handle_stream(self, stream, address):
        self._stream = stream
        self._stream.read_until_close(None, self.handle_read)

    def handle_read(self, data):
        self._stream.write(data)

if __name__ == '__main__':
    server = EchoServer()
    server.bind(25000)
    server.start(1)
    IOLoop.instance().start()
    IOLoop.instance().close()
