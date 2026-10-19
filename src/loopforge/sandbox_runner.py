"""Runs INSIDE the sandbox subprocess. Standalone: imports only the stdlib.

Protocol (one JSON object per line on the original stdout):

    {"t": "ready", "limits": [...], "alarm": bool}      limits actually applied
    {"t": "fatal", "error": "..."}                      candidate could not load
    {"t": "run", "i": 0, "seconds": 0.01, "tour": [...]}   or "error": "..."
    {"t": "done"}

The parent NEVER trusts anything here: it re-validates every tour and computes
every score itself. The worst a misbehaving candidate can do through this
channel is produce a tour that then fails validation.

Defense in depth (best effort, see docs/SANDBOX.md for the honest threat model):
  * OS resource limits (CPU time, memory, file size) where the platform has them
  * a per-instance alarm that interrupts runaway pure-Python loops
  * stdin/stdout/stderr redirected to /dev/null while candidate code runs
  * a restricted builtins table (no open/exec/eval) and an import blocklist
"""

import builtins
import json
import math
import os
import signal
import sys
import time

MAX_TOUR_LEN = 100_000

BLOCKED_IMPORTS = frozenset(
    {
        "os", "sys", "subprocess", "socket", "ssl", "ctypes", "shutil", "pathlib",
        "tempfile", "glob", "importlib", "imp", "multiprocessing", "threading",
        "_thread", "concurrent", "asyncio", "signal", "resource", "urllib", "http",
        "ftplib", "smtplib", "telnetlib", "requests", "pickle", "marshal", "shelve",
        "sqlite3", "builtins", "gc", "inspect", "code", "codeop", "runpy", "atexit",
        "posix", "nt", "_io", "io", "fcntl", "mmap", "pty", "select", "selectors",
    }
)

REMOVED_BUILTINS = frozenset(
    {"open", "exec", "eval", "compile", "input", "breakpoint", "exit", "quit",
     "help", "__import__", "memoryview"}
)


class _TimeLimit(BaseException):
    """Raised by the alarm handler. BaseException so ordinary `except Exception` misses it."""


def _emit(channel, message):
    channel.write(json.dumps(message) + "\n")
    channel.flush()


def _apply_limits(per_instance, n_instances, memory_mb):
    """Apply whatever OS limits this platform supports; return their names."""
    applied = []
    try:
        import resource
    except ImportError:  # Windows
        return applied

    def try_limit(name, which, value):
        try:
            resource.setrlimit(which, (value, value))
            applied.append(name)
        except (ValueError, OSError):
            pass

    try_limit("cpu", resource.RLIMIT_CPU, int(math.ceil(per_instance * n_instances)) + 3)
    try_limit("memory", resource.RLIMIT_AS, int(memory_mb) * 1024 * 1024)
    try_limit("files", resource.RLIMIT_FSIZE, 0)
    try_limit("core", resource.RLIMIT_CORE, 0)
    return applied


def _candidate_builtins():
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Only restrict imports made by the candidate itself; the standard
        # library may import whatever it needs internally. We look at the real
        # calling frame instead of the `globals` argument, because a candidate
        # can omit or fake that argument (e.g. a bare __import__('os')).
        caller = sys._getframe(1).f_globals.get("__name__")
        if caller == "candidate":
            top = name.split(".")[0]
            if top in BLOCKED_IMPORTS:
                raise ImportError("import of %r is not allowed in the sandbox" % top)
        return real_import(name, globals, locals, fromlist, level)

    safe = {k: v for k, v in vars(builtins).items() if k not in REMOVED_BUILTINS}
    safe["__import__"] = guarded_import
    return safe


def main():
    payload = json.loads(sys.stdin.buffer.read())
    instances = payload["instances"]
    per_instance = float(payload["per_instance_seconds"])
    memory_mb = payload["memory_mb"]

    # Keep a private copy of the real stdout for the protocol, then point fd 0/1
    # at /dev/null so candidate prints (even from C code) cannot corrupt it.
    global _CHANNEL
    channel = _CHANNEL = os.fdopen(os.dup(1), "w", buffering=1)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)

    limits = _apply_limits(per_instance, len(instances), memory_mb)
    has_alarm = hasattr(signal, "setitimer")
    if has_alarm:

        def on_alarm(signum, frame):
            raise _TimeLimit()

        signal.signal(signal.SIGALRM, on_alarm)

    _emit(channel, {"t": "ready", "limits": limits, "alarm": has_alarm})
    os.dup2(devnull, 2)  # silence stderr only after startup problems were visible

    def arm():
        if has_alarm:
            signal.setitimer(signal.ITIMER_REAL, per_instance)

    def disarm():
        if has_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)

    # --- load the candidate ---
    namespace = {"__name__": "candidate", "__builtins__": _candidate_builtins()}
    try:
        code = compile(payload["source"], "<candidate>", "exec")
        arm()
        try:
            exec(code, namespace)
        finally:
            disarm()
    except _TimeLimit:
        _emit(channel, {"t": "fatal", "error": "timed out while loading candidate code"})
        return
    except BaseException as exc:
        _emit(channel, {"t": "fatal", "error": ("%s: %s" % (type(exc).__name__, exc))[:300]})
        return

    solve = namespace.get("solve")
    if not callable(solve):
        _emit(channel, {"t": "fatal", "error": "source does not define a callable named 'solve'"})
        return

    # --- run it, failing fast: one bad instance invalidates the candidate ---
    for i, instance in enumerate(instances):
        points = [tuple(p) for p in instance]
        start = time.perf_counter()
        error = None
        tour = None
        try:
            arm()
            try:
                tour = solve(points)
            finally:
                disarm()
        except _TimeLimit:
            error = "timed out (over %.2fs on one instance)" % per_instance
        except BaseException as exc:  # includes SystemExit and MemoryError
            error = ("%s: %s" % (type(exc).__name__, exc))[:300]
        seconds = time.perf_counter() - start

        if error is None:
            if not isinstance(tour, (list, tuple)):
                error = "returned %s, expected a list" % type(tour).__name__
            elif len(tour) > MAX_TOUR_LEN:
                error = "tour has %d entries, which is more than the allowed %d" % (
                    len(tour), MAX_TOUR_LEN)

        message = {"t": "run", "i": i, "seconds": seconds}
        if error is None:
            message["tour"] = list(tour)
            try:
                line = json.dumps(message)
            except (TypeError, ValueError, OverflowError, RecursionError):
                error = "tour contains values that cannot be serialized"
        if error is not None:
            message = {"t": "run", "i": i, "seconds": seconds, "error": error}
        _emit(channel, message)
        if error is not None:
            break

    _emit(channel, {"t": "done"})


_CHANNEL = None

if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:  # a bug in the runner itself
        try:
            crash = {"t": "fatal", "error": ("runner crashed: %s" % exc)[:300]}
            if _CHANNEL is not None:
                _emit(_CHANNEL, crash)
            else:
                os.write(1, (json.dumps(crash) + "\n").encode())
        except OSError:
            pass
