# signal_handling.py
#
# This example illustrates how you might handle a Unix signal from Curio.
# The basic idea is that you need to install a standard signal handler
# using Python's built-in signal module.  That handler then communciates
# with a Curio task using a UniversalEvent (or a UniversalQueue).

import signal
import os
import curio

signal_evt = curio.UniversalEvent()

# Ordinary Python signal handler.
def sig_handler(signo, frame):
    signal_evt.set()

# A Curio task waiting for an event
async def coro():
    print("Waiting....")
    await signal_evt.wait()
    print("Got a signal!")

# Set up and execution
def main():
    signal.signal(signal.SIGHUP, sig_handler)
    print("Send me a SIGHUP", os.getpid())
    curio.run(coro)

if __name__ == '__main__':
    main()

