import json
from cgi import parse_header
from logging import getLogger
from collections import deque
from contextlib import suppress
from urllib.parse import urlparse, urlunparse, ParseResult, urljoin, parse_qsl

import h11

from .network import open_connection
from .errors import HttpError


logger = getLogger(__name__)


async def get(url, *, params=None, headers=None, allow_redirects=False):
    async with Session() as client:
        response = await client.get(
            url,
            params=params,
            headers=headers,
            allow_redirects=allow_redirects)
        response.raise_for_status()
        return response


class Connection:
    def __init__(self, host, port, ssl):
        self.host = host
        self.port = port
        self.ssl = ssl

        self.socket = None
        self.state = None

    def __repr__(self):
        return '{name}(host={self.host}, port={self.port}, socket={self.socket})'.format(
            name=self.__class__.__name__, self=self)

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def open(self):
        sock_args = {
            'host': self.host,
            'port': self.port,
        }
        if self.ssl:
            sock_args.update(
                ssl=self.ssl,
                server_hostname=self.host,
            )
        self.socket = await open_connection(**sock_args)
        self.state = h11.Connection(our_role=h11.CLIENT)
        logger.info('Opened connection: {}'.format(self))

    async def close(self):
        await self.socket.close()
        self.socket = self.state = None
        logger.debug('Closed connection: {}'.format(self))

    async def receive(self, maxsize=2048):
        while True:
            event = self.state.next_event()
            if event is not h11.NEED_DATA:
                return event
            data = await self.socket.recv(maxsize)
            self.state.receive_data(data)

    async def request(self, request, data=None):
        await self._send(request)
        if data is not None:
            await self._send(h11.Data(data=data))
        await self._send(h11.EndOfMessage())
        raw_response = await self.receive()
        raw_body = await self.receive_response_body()
        return raw_response, raw_body

    async def receive_response_body(self, maxsize=2048):
        """ iterate over raw response body, maxsize bytes at a time. """
        body = b''
        while True:
            event = await self.receive(maxsize)
            if isinstance(event, h11.EndOfMessage):
                return body
            if not isinstance(event, h11.Data):
                raise TypeError('Unknown event type: {}'.format(type(event)))
            body += event.data

    async def _send(self, event):
        logger.debug('Connection: {}, Sending event: {}'.format(self, event))
        data = self.state.send(event)
        await self.socket.sendall(data)


class Session:
    def __init__(self):
        self.connections = deque()

    def __repr__(self):
        return '{name}(connections={self.connections})'.format(name=type(self).__name__, self=self)

    async def __aenter__(self):
        logger.debug('Opened session: {}'.format(self))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for connection in self.connections:
            await connection.close()
        logger.debug('Closed session: {}'.format(self))

    async def get(self, url, *, params=None, headers=None, allow_redirects=False):
        """ Perform HTTP GET request. """
        return await self.request(
            'GET', url,
            params=params,
            headers=headers,
            allow_redirects=allow_redirects)

    async def post(self, url, *, params=None, headers=None, data=None, allow_redirects=False):
        """ Perform HTTP POST request. """
        return await self.request(
            'POST', url,
            params=params,
            headers=headers,
            data=data,
            allow_redirects=allow_redirects)

    async def request(self, method, url, *, params=None, headers=None, data=None, allow_redirects=False):
        """ Perform HTTP request. """
        url = url if isinstance(url, ParseResult) else urlparse(url)
        method = method.upper()
        response = await self._request(method, url, params=params, headers=headers, data=data)
        if allow_redirects:
            await self._redirect_loop(response)
        return response

    async def _request(self, method, url, *, params=None, headers=None, data=None):
        request, body = self._prepare_request(method, url, params=params, headers=headers, data=data)
        connection = Connection(
            host=url.hostname,
            port=url.port or 80,
            ssl=url.scheme == 'https')
        await connection.open()
        self.connections.append(connection)
        raw_response, raw_body = await connection.request(request, body)
        return Response(
            raw_response, raw_body,
            url=url,
            request=request,
            connection=connection)

    async def _redirect_loop(self, response):
        while response.is_redirect:
            response.history.append(response)
            url = urljoin(response.url, response.headers['location'])
            response = await self._request(response.method, url)

    def _prepare_request(self, method, url, params=None, headers=None, data=None):
        if params:
            query_vars = params.update(parse_qsl(url.query, keep_blank_values=True))
            query = b','.join(b'%s=%s' % (key, value) for key, value in query_vars.items())
            url = url._replace(query=query)

        target = urlunparse(url._replace(scheme='', netloc=''))

        headers = headers or {}
        headers.setdefault('Host', url.hostname)
        if data is not None and 'Transfer-Encoding' not in headers:
            headers['Content-Length'] = str(len(data)).encode('utf-8')

        with suppress(AttributeError):
            data = data.encode('utf-8')

        request = h11.Request(
            method=method,
            target=target,
            headers=list(headers.items()),
        )
        return request, data


class Response:
    """ Http async request """

    def __init__(self, raw_response, raw_body, *, url, request, connection):
        self._response = raw_response
        self.binary = raw_body
        self.url = url
        self.request = request
        self.connection = connection
        self.history = deque()

    def __repr__(self):
        return 'Response(status_code={self.status_code}, url={self.url})'.format(self=self)

    def __getattr__(self, item):
        with suppress(AttributeError):
            return getattr(self._response, item)
        with suppress(AttributeError):
            return getattr(self.request, item)
        return getattr(self.url, item)

    @property
    def http_verison(self):
        return self._response.http_version.decode('utf-8')

    @property
    def headers(self):
        return {
            key.decode('utf-8'): value.decode('utf-8')
            for key, value in self._response.headers
        }

    @property
    def is_redirect(self):
        return 'location' in self.headers and 301 <= self.status_code < 400

    @property
    def text(self):
        """ Return the full response body as a string. """
        if not self.binary:
            raise HttpError('Must call set_body before')
        encoding = self._encoding_from_headers()
        return self.binary.decode(encoding)

    @property
    def json(self):
        """ Return the full response body as parsed JSON. """
        if not self.binary:
            raise HttpError('Must call set_body before')
        return json.loads(self.binary.decode('utf-8'))

    def raise_for_status(self):
        """ Raises HTTPError, if status-code >= 400. """
        if 400 <= self.status_code < 500:
            raise HttpError('Request {self} got Client Error'.format(self=self))
        if 500 <= self.status_code < 600:
            raise HttpError('Request {self} got Server Error'.format(self=self))

    def _encoding_from_headers(self):
        try:
            content_type = self.headers['content-type']
        except KeyError:
            return
        content_type, parameters = parse_header(content_type)
        with suppress(KeyError):
            return parameters['charset']
        if 'text' in content_type:
            return 'ISO-8859-1'
