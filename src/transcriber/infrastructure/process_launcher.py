"""Linux-only Docker subprocess guard: kill decoder if its worker dies."""
import ctypes
import os
import signal
import resource
import sys

if __name__ == '__main__':
    expected_parent = int(sys.argv[1])
    if sys.argv[2] == 'ffprobe':
        resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    if sys.platform == 'linux':
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL) != 0:
            raise OSError(ctypes.get_errno(), 'prctl failed')
        if os.getppid() != expected_parent:
            sys.exit(1)
    os.execvp(sys.argv[2], sys.argv[2:])
