# Example of making an SSL connection and downloading data

import curio

async def main():
    sock = await curio.open_connection('www.python.org', 443,
                                       ssl=True, server_hostname='www.python.org')
    async with sock:
        await sock.sendall(b'GET / HTTP/1.0\r\nHost: www.python.org\r\n\r\n')
        chunks = []
        while True:
            chunk = await sock.recv(10000)
            if not chunk:
                break
            chunks.append(chunk)

    response = b''.join(chunks)
    print(response.decode('latin-1'))


if __name__ == '__main__':
    try:
        curio.run(main())
    except KeyboardInterrupt:
        pass
