"""Run the attach tree inside the capacity controller Pod's finite cgroup."""
import os
from pathlib import Path
import signal
import subprocess
import time

import execute


def allocation(template):
    relative = Path('/proc/self/cgroup').read_text().strip().split(':', 2)[-1]
    root = Path('/sys/fs/cgroup') / relative.lstrip('/')
    files = ('cpu.max', 'memory.max', 'memory.swap.max')
    return execute.finite_scope(template, {name: (root/name).read_text().strip() for name in files})


def group_present(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    return True


def run(argv, env, timeout, record):
    # The Pod also runs the uploader. End only the process group created for this attach.
    child = subprocess.Popen(argv, env=env, start_new_session=True)
    try:
        child.wait(timeout=timeout)
        if child.returncode:
            raise RuntimeError('K8S_CONTROLLER_ATTACH_FAILED')
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if not group_present(child.pid):
                break
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                break
            until = time.monotonic() + 2
            while group_present(child.pid) and time.monotonic() < until:
                child.poll()
                time.sleep(.05)
        absent = not group_present(child.pid)
        record({'processGroup': child.pid, 'returncode': child.poll(), 'absent': absent})
        if not absent:
            raise RuntimeError('K8S_CONTROLLER_ATTACH_GROUP_REMAINS')
