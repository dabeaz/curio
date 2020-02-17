# guikernel.py
#
# Contributed by George Zhang.
#
# An example of using tkinter's loop to run curio's loop.
#
# Note that all operations with tkinter should use `run_in_main` to
# delegate work to curio's main thread (which is where tkinter's
# mainloop is also running). Just be careful with tkinter and threads as
# tkinter isn't thread safe :(


# --- Standard library imports ---

import tkinter

from collections import deque
from contextlib import closing, contextmanager, suppress, ExitStack
from functools import wraps
from itertools import count
from inspect import getgeneratorlocals, getgeneratorstate, GEN_RUNNING, GEN_CLOSED
from time import monotonic


# --- Curio imports ---

from curio.errors import CurioError
from curio.kernel import run as curio_run, Kernel
from curio.sched import SchedBarrier
from curio import current_task, ignore_after, spawn
from curio.thread import spawn_thread, AWAIT
from curio.traps import _get_kernel, _scheduler_wait


__all__ = [
    # Main kernel with a `tkinter.Tk()` instance upon receiving work
    "TkKernel",

    # New errors for different aspects of the new kernel
    "TkCurioError", "EventTaskOnly", "NoEvent", "CloseWindow",

    # New traps
    "_wait_event", "_pop_event",

    # New higher level async functions for interacting with the kernel
    "current_toplevel", "pop_event",

    # Utility functions
    "iseventtask", "run_in_main",
]


# --- New kernel for tkinter ---

class TkKernel(Kernel):

    _tk_events = (
        "<Activate>", "<Circulate>", "<Colormap>", "<Deactivate>",
        "<FocusIn>", "<FocusOut>", "<Gravity>", "<Key>", "<KeyPress>",
        "<KeyRelease>",  "<MouseWheel>", "<Property>",
    )

    _other_events = (
        "<Button>", "<ButtonPress>", "<ButtonRelease>", "<Configure>",
        "<Enter>", "<Expose>", "<Leave>", "<Map>", "<Motion>",
        "<Reparent>", "<Unmap>", "<Visibility>",
    )


    @wraps(Kernel.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._toplevel = None
        self._event_queue = deque()
        self._event_wait = SchedBarrier()


    # Copied from curio 0.10 (ensures that kernel's toplevel is closed)
    def __exit__(self, ty, val, tb):
        if self._shutdown_funcs is not None:
            self.run(shutdown=True)


    def _run_coro(kernel):

        # --- Main loop preparations ---

        _runner = super()._run_coro()
        runner_send = _runner.send
        runner_send(None)

        toplevel = kernel._toplevel

        event_queue = kernel._event_queue
        event_queue_append = event_queue.append
        event_queue_popleft = event_queue.popleft

        event_wait = kernel._event_wait
        event_wait_pop = event_wait.pop

        tk_runner = None    # Generator that holds the tkinter loop
        frame = None        # Looping widget (`tkinter.Frame`)

        coro = None         # Coroutine passed in from `.run`
        result = None       # Result from `tk_runner`

        # Get variables from `_runner`
        runner_locals = getgeneratorlocals(_runner)
        _reschedule_task = runner_locals["_reschedule_task"]


        # --- Tkinter helper functions ---

        @contextmanager
        def destroying(widget):
            try:
                yield widget
            finally:
                with suppress(tkinter.TclError):
                    widget.destroy()

        @contextmanager
        def bind(widget, func, events):
            widget_bind = widget.bind
            widget_unbind = widget.unbind
            bindings = [(event, widget_bind(event, func, "+")) for event in events]
            try:
                if len(bindings) == 1:
                    yield bindings[0]
                else:
                    yield bindings
            finally:
                for info in bindings:
                    widget_unbind(*info)

        @contextmanager
        def protocol(toplevel, func):
            toplevel.protocol("WM_DELETE_WINDOW", func)
            try:
                yield
            finally:
                toplevel.protocol("WM_DELETE_WINDOW", toplevel.destroy)

        def tk_send(
            info,
            *,
            reschedule=False,
            _unsafe_states=frozenset({GEN_RUNNING, GEN_CLOSED}),
        ):
            if not tk_runner or getgeneratorstate(tk_runner) in _unsafe_states:
                if reschedule:
                    frame.after(1, lambda: tk_send(info, reschedule=True))
                return False

            try:
                tk_runner.send(info)
            except BaseException as e:
                nonlocal result
                if isinstance(e, StopIteration):
                    result = e.value
                else:
                    result = e
                with suppress(tkinter.TclError):
                    frame.destroy()
            finally:
                return True

        @contextmanager
        def ensure_after(secs, widget):
            if secs is None:
                yield

            else:
                tm = max(int(secs*1000), 1)
                callback = lambda: tk_send(
                    "SLEEP_WAKE" if secs else "READY",
                    reschedule=True,
                )
                id_ = widget.after(tm, callback)
                try:
                    yield
                finally:
                    widget.after_cancel(id_)


        # --- Tkinter callbacks ---

        # Decorator to return "break" for tkinter callbacks
        def tkinter_callback(func):
            @wraps(func)
            def _wrapped(*args):
                func(*args)
                return "break"
            return _wrapped

        # Functions for event callbacks
        @tkinter_callback
        def send_tk_event(event):
            if event.widget is toplevel:
                event_queue_append(event)
                if event_wait:
                    tk_send("EVENT_WAKE")

        @tkinter_callback
        def send_other_event(event):
            if event.widget is not toplevel:
                event_queue_append(event)
                if event_wait:
                    tk_send("EVENT_WAKE")

        @tkinter_callback
        def send_destroy_event(event):
            if event.widget is toplevel:
                event_queue_append(event)
                if event_wait:
                    frame.after(1, lambda: tk_send("EVENT_WAKE"))

        @tkinter_callback
        def close_window():
            if event_wait:
                tk_send("CLOSE_WINDOW", reschedule=True)


        # --- Internal loop (driven by tkinter's loop) ---

        def _tk_run_task(frame, coro):

            val = exc = None    # Info from `spawn` task
            tk_task = None      # Task to wait for its completiong

            with destroying(frame):

                val, exc = runner_send(spawn(coro))
                if exc:
                    raise exc
                tk_task = val
                tk_task.report_crash = False
                del coro, val, exc

                while True:
                    if (
                        (tk_task and tk_task.terminated)
                        or (not kernel._ready and not tk_task)
                    ):
                        if tk_task:
                            tk_task._joined = True
                            return (tk_task.next_value, tk_task.next_exc)
                        else:
                            return (None, None)

                    # Set the timeout for our `.after` callback.
                    # Note that the selector is also considered in this
                    # conditional as we cannot add a callback to a selector.
                    if kernel._ready or kernel._selector.get_map() or not tk_task:
                        timeout = 0
                    else:
                        timeout = kernel._sleepq.next_deadline(monotonic())

                    # This makes sure that the loop will continue. We suspend
                    # here only to receive any `tkinter` events.
                    with ensure_after(timeout, frame):
                        info = (yield)

                    if info == "EVENT_WAKE":
                        # Wake all tasks waiting for an event
                        for task in event_wait_pop(len(event_wait)):
                            _reschedule_task(task)

                    elif info == "CLOSE_WINDOW":
                        # Raise an error on event waiting tasks
                        # Note: This will NOT raise the error on any
                        # blocking operation; only `_wait_event` will raise
                        # this exception.
                        for task in event_wait_pop(len(event_wait)):
                            _reschedule_task(task, exc=CloseWindow("X was pressed"))

                    # Only remove events if there are event tasks or if
                    # the queue is filling up.
                    event_tasks = [t for t in kernel._tasks.values() if iseventtask(t)]
                    if event_tasks:
                        offset = min(t.next_event for t in event_tasks)
                        if offset > 0:
                            for _ in range(offset):
                                event_queue_popleft()
                            for task in event_tasks:
                                task.next_event -= offset
                    # There aren't any event tasks to notice this change.
                    elif len(event_queue) > 100:
                        event_queue.clear()

                    # Run using `schedule()`. Supplying `None` as the argument
                    # means a task doing `while True: await schedule()` can block
                    # the loop as the ready queue will never be empty.
                    print("HERE")
                    _, exc = runner_send(sleep(0))
                    if exc:
                        raise exc


        # --- Main loop ---

        # Setup the main cleanup stack
        with ExitStack() as stack:
            enter = stack.enter_context

            # Create toplevel window
            toplevel = kernel._toplevel = enter(destroying(tkinter.Tk()))

            # Ensure closing of original runner
            enter(closing(_runner))

            # Bind all events
            enter(bind(toplevel, send_tk_event, kernel._tk_events))
            enter(bind(toplevel, send_other_event, kernel._other_events))
            enter(bind(toplevel, send_destroy_event, ("<Destroy>",)))
            enter(protocol(toplevel, close_window))

            while True:

                # If an exception happened in `tk_runner`, end the
                # kernel and raise the exception
                if isinstance(result, BaseException):
                    raise result

                # Get the next coroutine to run :D
                coro = (yield result)
                frame = tkinter.Frame(toplevel)
                tk_runner = _tk_run_task(frame, coro)
                coro = None

                # Setup the cycle's cleanup stack
                with ExitStack() as inner_stack:
                    inner_enter = inner_stack.enter_context
                    inner_enter(destroying(frame))
                    inner_enter(closing(tk_runner))

                    # Start the cycle :)
                    tk_send(None)
                    with suppress(tkinter.TclError):
                        frame.wait_window()

                    # Exceptions in the loop
                    if getgeneratorstate(tk_runner) != GEN_CLOSED:
                        raise RuntimeError("Kernel frame destroyed before task finished")
                    try:
                        if not toplevel.winfo_exists():
                            raise RuntimeError("Kernel toplevel destroyed before shutdown")
                    except tkinter.TclError:
                        raise RuntimeError("Kernel toplevel destroyed before shutdown")


# --- New errors and exceptions ---

# Base class for new errors
class TkCurioError(CurioError):
    pass


# Requested trap is for event tasks
# (tasks with `.next_event` set to a integer >= 0)
class EventTaskOnly(TkCurioError):
    pass


# An unread event could not be retrieved at this time :(
class NoEvent(TkCurioError):
    pass


# The window's "X" button was pressed
class CloseWindow(TkCurioError):
    pass


# --- New traps / getters ---

async def current_toplevel():
    """
    Return the current toplevel `tkinter.Tk` instance for this kernel.
    """
    kernel = await _get_kernel()
    return kernel._toplevel


def iseventtask(task):
    """
    Return True if `task` is considered an event task, meaning one that
    acts on `tkinter` events.
    Return False otherwise.
    """
    return getattr(task, "next_event", -1) >= 0


# Wait for a new event to be received (similar to `_read_wait`)
async def _wait_event():
    task = await current_task()
    if not iseventtask(task):
        raise EventTaskOnly("Trap for event tasks only")
    kernel = await _get_kernel()
    if len(kernel._event_queue) <= task.next_event:
        await _scheduler_wait(kernel._event_wait, "EVENT_WAIT")


# Pop an unread event off the event queue (similar to a `socket.recv`)
async def _pop_event():
    task = await current_task()
    if not iseventtask(task):
        raise EventTaskOnly("Trap for event tasks only")
    kernel = await _get_kernel()
    try:
        event = kernel._event_queue[task.next_event]
    except IndexError:
        raise NoEvent("No unread event for task") from None
    else:
        # Note: the "popping" is just advancing this counter so that the
        # events are not repeated. This lets us use just one `deque` to
        # store the events and not waste memory.
        task.next_event += 1
        return event


async def pop_event(blocking=True):
    """
    Wait for and return the next unread event.
    Raises `NoEvent` if there is no new event and `blocking` is False.
    """
    if not blocking:
        return await _pop_event()
    while True:
        try:
            return await _pop_event()
        except NoEvent:
            await _wait_event()


# --- Other spicy stuff to spice up your async code ---

class aevents:
    """
    Asynchronous iterable that yields events upon request. Can be used in
    an `async for` loop for simple event retrieval.
    """

    def __init__(self, *, timeout=None):
        self._timeout = timeout

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._timeout is None:
            return await pop_event()
        else:
            return await ignore_after(self._timeout, pop_event())


# Dah... this should be in itertools / builtins.
# Speaking of which, where are the builtin `aiter` and `anext`!?
class aenumerate:
    """
    The `aenumerate` object yields pairs containing a count (from
    `start`, which defaults to 0) and a value asynchronously yielded by
    the `aiterable` argument.
    """

    def __init__(self, aiterable, start=0):
        self._anext = aiterable.__anext__
        self._count = count(start)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return (next(self._count), await self._anext())


# Helper function for `run_in_main`
async def _call(func, args, kwargs):
    return func(*args, **kwargs)


async def run_in_main(func_, *args, **kwargs):
    """
    Run and return `func_(*args, **kwargs)` in the kernel's thread.
    Note that this should only be restricted to tkinter calls.
    """
    # Note: the argument is `func_` to prevent name clashes in `kwargs`.
    # This can become a positional only parameter (introduced in Python
    # 3.8) once curio deprecates its usage in Python 3.6 and 3.7.
    async with spawn_thread():
        return AWAIT(_call(func_, args, kwargs))


# --- Examples :D ---

import curio

async def test():

    toplevel = await current_toplevel()
    canvas = tkinter.Canvas(toplevel, highlightthickness=0)
    canvas.pack(expand=True, fill="both")

    task = await curio.current_task()
    task.next_event = 0 # Make current task an event task
    assert iseventtask(task)

    x = y = None
    lastx = lasty = None

    try:
        async for i, event in aenumerate(aevents()):
            if str(event.type) in {"Enter", "Motion"}:
                x, y = event.x, event.y
                if lastx is None:
                    lastx, lasty = x, y

                canvas.create_line(lastx, lasty, x, y, width=5)
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="black")
                lastx, lasty = x, y

    except CloseWindow:
        pass

    if False: # Toggle this to try out `run_in_main`'s power

        async with curio.spawn_thread():
            try:
                print("not in main thread")
                print(toplevel.winfo_exists())

            except RuntimeError as e:
                print(repr(e))

            AWAIT(run_in_main(lambda: (
                print("in main thread"),
                print(toplevel.winfo_exists()),
            )))

        # Note that `CloseWindow` exceptions don't pop up here
        await curio.sleep(5)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    from curio.debug import schedtrace
    with TkKernel(debug=[schedtrace]) as ttk:
        ttk.run(test)
