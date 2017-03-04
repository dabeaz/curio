# Example of launching a subprocess and reading streaming output

from curio import subprocess
import curio


async def main():
    p = subprocess.Popen(['ping', 'www.python.org'], stdout=subprocess.PIPE)
    async for line in p.stdout:
        print('Got:', line.decode('ascii'), end='')


if __name__ == '__main__':
    try:
        curio.run(main)
    except KeyboardInterrupt:
        pass
