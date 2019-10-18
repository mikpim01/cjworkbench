import array
import ctypes
import importlib
import os
from pathlib import Path
import signal
import sys
import socket
import traceback
from typing import Callable
import cjwkernel.pandas.main
from . import protocol


libc = ctypes.CDLL("libc.so.6", use_errno=True)
libcapng = ctypes.CDLL("libcap-ng.so.0", use_errno=True)
# Yes, there's a Python version of capng ... but it's not on PyPi and
# [2019-10-11] pipenv is a crazy pain in the neck so we basically can't
# install it.
# <capng.h>
CAPNG_SELECT_BOTH = 48
# <linux/prctl.h>
PR_SET_NAME = 15
PR_CAPBSET_DROP = 24
PR_SET_NO_NEW_PRIVS = 38
# <linux/capability.h>
CAP_LAST_CAP = 37
# BEWARE: Docker, by default, disallows user-namespace cloning. We use Docker
# in development. Therefore we override Docker's seccomp profile to allow our
# clone() syscall to succeed. If you're adding to this list, also modify the
# seccomp profile we use in dev, unittest and integrationtest.
# <linux/sched.h>
CLONE_PARENT = 0x00008000
CLONE_NEWUSER = 0x10000000
CLONE_NEWCGROUP = 0x02000000
CLONE_NEWIPC = 0x08000000
CLONE_NEWPID = 0x20000000
CLONE_NEWNS = 0x00020000  # new mount namespace


def _call_c(lib, fn, *args):
    """
    Call a libc function; raise OSError if it returns a negative number.

    Raise AttributeError if libc does not have an `fn` function.
    """
    func = getattr(lib, fn)  # raise AttributeError

    retval = func(*args)
    if retval < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, "error calling %s(): %s" % (fn, os.strerror(errno)))
    return retval


_MODULE_STACK = ctypes.create_string_buffer(2 * 1024 * 1024)
"""
The memory area our child-module process will use for its stack.

Yup, this is low-level.
"""
_MODULE_STACK_POINTER = ctypes.c_void_p(
    ctypes.cast(_MODULE_STACK, ctypes.c_void_p).value + len(_MODULE_STACK)
)


# GLOBAL VARIABLES
#
# SECURITY: _any_ variable in "forkserver" is accessible to a "module" that it
# spawns. `del` will not delete the data.
#
# Our calling convention is: "forkserver uses global variables; module can see
# them." Rationale: to a malicious module, all variables are global anyway.
# "forkserver" should use very few variables, and they are all listed here.
module_main: Callable[..., None] = None
"""Function to call after sandboxing, with *message.args."""
sock: socket.socket = None
"""Socket "forkserver" uses to communicate with its parent."""
message: protocol.SpawnPandasModule = None
"""Arguments passed to the spawned module."""
stdout_read_fd: int = None
stdout_write_fd: int = None
stderr_read_fd: int = None
stderr_write_fd: int = None
is_uidmap_written_read_fd: int = None
is_uidmap_written_write_fd: int = None


def _should_sandbox(feature: str) -> bool:
    """
    Return `True` if we should call a particular sandbox function.

    This should _always_ return `True` on production code. The function only
    exists to help with unit testing.
    """
    if message.skip_sandbox_except:
        # test code only
        return feature in message.skip_sandbox_except
    else:
        # production code
        return True


def _sandbox_module():
    """
    Prevent module code from interacting with the rest of our system.

    Tasks with rationale ('[x]' means, "unit-tested"):

    [ ] Wait for forkserver to write uid_map
    [x] Close `sock` (so "forkserver" does not misbehave)
    [x] Close stdout/stderr (so modules do not flood logs; point
        stdout/stderr to `message.log_fd` instead)
    [x] Drop capabilities (like CAP_SYS_ADMIN)
    [x] Setuid to 1000
    [ ] Use chroot (so modules can't see other processes)
    """
    os.close(sock.fileno())  # Close `sock`
    global stdout_read_fd, stderr_read_fd
    os.close(stdout_read_fd)
    os.close(stderr_read_fd)
    stdout_read_fd = None
    stderr_read_fd = None

    # Wait for parent to close the is_uidmap_written pipe
    os.close(is_uidmap_written_write_fd)
    os.read(is_uidmap_written_read_fd, 1)
    os.close(is_uidmap_written_read_fd)

    _sandbox_stdout_stderr()
    if _should_sandbox("no_new_privs"):
        _sandbox_no_new_privs()
    # if _should_sandbox("setuid"):
    #     _sandbox_setuid()
    if _should_sandbox("drop_capabilities"):
        _sandbox_drop_capabilities()


def _sandbox_stdout_stderr():
    """
    Rewrite the fds 1 and 2 to become stdout_write_fd and stderr_write_fd.

    Close stdout_write_fd and stderr_write_fd and set them to `None`.

    After this, `sys.stdout` and `sys.stderr` will point to `stdout_write_fd`
    and `stderr_write_fd`. There will be no way to write to the _original_
    stdout and stderr (file descriptors 1 and 2) -- they will be closed.

    Why call this? Because by default, stdout and stderr are inherited from the
    parent process. In the parent, they are used for logging. User code must
    not be allowed to write to our server logs; therefore, user code must not
    be able to access the original stdout and stderr.
    """
    global stdout_write_fd, stderr_write_fd
    os.dup2(stdout_write_fd, 1)
    os.dup2(stderr_write_fd, 2)
    # Now close the originals (since we just duplicated them)
    os.close(stdout_write_fd)
    os.close(stderr_write_fd)
    stdout_write_fd = None
    stderr_write_fd = None


def _write_namespace_uidgid(pid: int) -> None:
    """
    Write /proc/self/uid_map and /proc/self/gid_map.

    Why call this? Because otherwise, the called code can do it for us. That
    would mean root in the child would be equal to root in the parent -- so the
    child could, for instance, modify files owned outside of it.

    ref: man user_namespaces(7).
    """
    Path(f"/proc/{pid}/uid_map").write_text("0 100000 65536")
    Path(f"/proc/{pid}/setgroups").write_text("deny")
    Path(f"/proc/{pid}/gid_map").write_text("0 100000 65536")


def _sandbox_drop_capabilities():
    """
    Drop all capabilities in the caller.

    Why call this? So if user code manages to setuid to root (which should be
    impossible), it still won't have permission to call dangerous kernel code.
    (For example: after dropping privileges, "pivot_root" will fail with
    EPERM, even for root.)

    ref: http://people.redhat.com/sgrubb/libcap-ng/
    """
    libcapng.capng_clear(CAPNG_SELECT_BOTH)  # cannot error
    _call_c(libcapng, "capng_apply", CAPNG_SELECT_BOTH)


def _sandbox_no_new_privs():
    """
    Prevent a setuid bit on a file from restoring capabilities.
    """
    _call_c(libc, "prctl", PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)


def _sandbox_setuid():
    """
    Drop root: switch to UID 1000.

    Why call this? Because Linux gives special capabilities to root (even after
    we drop privileges).

    ref: man setresuid(2)
    """
    os.setresuid(1000, 1000, 1000)
    os.setresgid(1000, 1000, 1000)


def cloned_module_main() -> int:
    # Aid in debugging a bit
    name = "cjwkernel-module:%s" % message.process_name
    _call_c(libc, "prctl", PR_SET_NAME, name.encode("utf-8"), 0, 0, 0)

    _sandbox_module()

    # Run the module code. This is what it's all about!
    #
    # It's normal for a module to raise an exception. That's probably a
    # developer error, and it's best to show the developer the problem --
    # exactly what `log_fd` is for. So we want to log exceptions to log_fd.
    #
    # SECURITY: it's possible for a module to try and fiddle with the stack or
    # heap to execute anything in memory. So this function might never return.
    # (Imagine `goto`.) That's okay -- we sandbox the module so it can't harm
    # us (aside from wasting CPU cycles), and we kill it after a timeout.
    try:
        module_main(*message.args)
    except:
        traceback.print_exc(sys.stderr.buffer.fileno())
        os._exit(1)

    # In the _common_ case ... exit here.
    os._exit(0)


_MODULE_MAIN_FUNC = ctypes.PYFUNCTYPE(ctypes.c_int)(cloned_module_main)


def spawn_module(sock: socket.socket, message: protocol.SpawnPandasModule) -> None:
    """
    Fork a child process; send its handle over `sock`; return.

    This closes all open file descriptors in the child: stdin, stdout, stderr,
    and `sock.fileno()`. The reason is SECURITY: the child will invoke
    user-provided code, so we bar everything it doesn't need. (Heck, it doesn't
    even get stdin+stdout+stderr!)

    There are three processes running concurrently here:

    * "parent": the Python process that holds a ForkServer handle. It sent
                `SpawnPandasModule` on `sock` and expects a response of
                `SpawnedPandasModule` (with "module_pid").
    * "forkserver": the forkserver_main() process. It called this function. It
                    has few file handles open -- by design. It spawns "module",
                    and sends "parent" the "module_pid" over `sock`.
    * "module": invokes `cjwkernel.pandas.main.main()`, using the file
                descriptors passed in `SpawnPandasModule`.
    """
    global stdout_read_fd, stdout_write_fd, stderr_read_fd, stderr_write_fd, is_uidmap_written_read_fd, is_uidmap_written_write_fd

    assert stdout_read_fd is None
    assert stdout_write_fd is None
    assert stderr_read_fd is None
    assert stderr_write_fd is None
    assert is_uidmap_written_read_fd is None
    assert is_uidmap_written_write_fd is None

    stdout_read_fd, stdout_write_fd = os.pipe()
    stderr_read_fd, stderr_write_fd = os.pipe()
    is_uidmap_written_read_fd, is_uidmap_written_write_fd = os.pipe()

    module_pid = _call_c(
        libc,
        "clone",
        _MODULE_MAIN_FUNC,
        _MODULE_STACK_POINTER,
        CLONE_PARENT | CLONE_NEWUSER | signal.SIGCHLD,
        0,
    )
    if module_pid < 0:
        raise OSError(ctypes.get_errno(), "clone() system call failed")
    assert module_pid != 0, "clone() should not return in the child process"

    os.close(stdout_write_fd)
    os.close(stderr_write_fd)
    stdout_write_fd = None
    stderr_write_fd = None

    os.close(is_uidmap_written_read_fd)
    is_uidmap_written_read_fd = None
    _write_namespace_uidgid(module_pid)
    os.close(is_uidmap_written_write_fd)
    is_uidmap_written_write_fd = None

    spawned_module = protocol.SpawnedPandasModule(
        module_pid, stdout_read_fd, stderr_read_fd
    )
    spawned_module.send_on_socket(sock)

    os.close(stdout_read_fd)
    os.close(stderr_read_fd)
    stdout_read_fd = None
    stderr_read_fd = None


def forkserver_main(_module_main: str, socket_fd: int) -> None:
    """
    Start the forkserver.

    The init protocol ("a" means "parent" [class ForkServer], "b" means,
    "child" [forkserver_main()]):

    1a. Parent invokes forkserver_main(), passing AF_UNIX fd as argument.
    1b. Child calls socket.fromfd(), establishing a socket connection.
    2a. Parent sends ImportModules.
    2b. Child imports modules in its main (and only) thread.
    3a. Parent LOCKs
    4a. Parent creates fds and sends them through SpawnPandasModule().
    4b. Child forks and sends parent the PID. The returned PID is a *direct*
        child of parent (not of child) -- it got there via double-fork with
        "parent" having PR_SET_CHILD_SUBREAPER.
    5a. Parent receives PID from client.
    6a. Parent UNLOCKs
    7a. Parent reads from its fds and polls PID.

    For shutdown, the client simply closes its connection.

    The inevitable race: if "parent" doesn't read "module_pid" from the other
    end of "sock" and wait() for it, then nothing will wait() for the module
    process after it dies and it will become a zombie.
    """
    # Close fd=0 (stdin). No children should be able to read from stdin; and
    # forkserver_main has no reason to read from stdin, either.
    os.close(0)

    global module_main
    module_main_module_name, module_main_name = _module_main.rsplit(".", 1)
    module_main_module = importlib.import_module(module_main_module_name)
    module_main = module_main_module.__dict__[module_main_name]

    # 1b. Child establishes socket connection
    #
    # Note: we don't put this in a `with` block, because that would add a
    # finalizer. Finalizers will run in the "module_pid" process if
    # cjwkernel.pandas.main() raises an exception ... but the "module_pid"
    # process closes the socket before calling cjwkernel.pandas.main(), so the
    # finalizer would crash.
    global sock  # see GLOBAL VARIABLES comment
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, fileno=socket_fd)

    # 2b. Child imports modules in its main (and only) thread
    imports = protocol.ImportModules.recv_on_socket(sock)
    for im in imports.modules:
        __import__(im)

    while True:
        global message  # see GLOBAL VARIABLES comment
        try:
            # raise EOFError, RuntimeError
            message = protocol.SpawnPandasModule.recv_on_socket(sock)
        except EOFError:
            # shutdown: client closed its connection
            return

        # 4b. Child forks and sends parent the PID
        #
        # The _child_ sends `SpawnedPandasModule` over `sock`, because only
        # the child knows the sub-child's PID.
        spawn_module(sock, message)
