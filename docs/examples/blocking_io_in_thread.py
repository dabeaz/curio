from curio import run, spawn, tcp_server, run_in_thread

async def echo_client(client, addr):
    print('Connection from', addr)
    while True:
        data = await client.recv(1000)
        if not data:
            break

        # Temporarily enter blocking mode
        with client.blocking() as _client:
            await run_in_thread(_client.sendall, data)

    print('Connection closed')

if __name__ == '__main__':
    run(tcp_server('', 25000, echo_client))
