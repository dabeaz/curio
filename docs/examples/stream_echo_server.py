from curio import run, tcp_server

async def echo_client(client, addr):
    print('Connection from', addr)
    s = client.as_stream()
    while True:
        data = await s.read(1000)
        if not data:
            break
        await s.write(data)
    print('Connection closed')

if __name__ == '__main__':
    run(tcp_server('', 25000, echo_client))
