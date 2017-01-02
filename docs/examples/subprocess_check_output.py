import curio
from curio import subprocess

async def main():
    try:
        out = await subprocess.check_output(['netstat', '-a'])
    except subprocess.CalledProcessError as e:
        print('It failed!', e)

if __name__ == '__main__':
    curio.run(main())
