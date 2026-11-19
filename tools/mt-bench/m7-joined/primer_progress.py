"""Monotonic stall budget for a source-owned durable tenant count."""
import json
import subprocess
import time


class ProgressWindow:
    def __init__(self, seconds, *, now=time.monotonic, completed=0):
        self.seconds = seconds
        self.now = now
        self.completed = completed
        self.deadline = now() + seconds

    def observe(self, completed):
        at = self.now()
        if type(completed) is not int or completed <= self.completed or at >= self.deadline:
            return False
        self.completed = completed
        self.deadline = at + self.seconds
        return True

    def remaining(self):
        return max(0, self.deadline - self.now())


class ComposePrimerWait:
    """Supervise the attached Compose child using the primer's bind-mounted checkpoints."""

    def __init__(self, state, operation, seconds, stage):
        self.provision = operation == 'provision'
        self.path = state / ('provisioned.json' if self.provision else 'tenants.json')
        self.checkpoint_version = None
        self.stage = stage
        self.stage['primerStallSeconds'] = seconds
        self.stage['completedTenants'] = 0
        self.checkpoint()

    def checkpoint(self):
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return self.stage['completedTenants']
        # The source fsyncs and renames each checkpoint. A new file only
        # prompts a read; only a higher durable count renews the window.
        version = (stat.st_ino, stat.st_mtime_ns)
        if version != self.checkpoint_version:
            try:
                with self.path.open() as stream:
                    value = json.load(stream)
                rows = value if self.provision else value['tenants']
                count = len({row['id'] for row in rows})
            except (ValueError, TypeError, KeyError):
                raise RuntimeError('M7_PRIMER_CHECKPOINT_INVALID') from None
            self.stage['completedTenants'] = max(self.stage['completedTenants'], count)
            self.checkpoint_version = version
        return self.stage['completedTenants']

    def __call__(self, argv, *, timeout, input=None, **options):
        # Both stdout and stderr already go to the runner's phase files.
        if input is not None or subprocess.PIPE in (options['stdout'], options['stderr']):
            raise ValueError('M7_PRIMER_FILE_OUTPUT_REQUIRED')
        # Mutation preflight runs before this call and has its own timeout.
        self.window = ProgressWindow(self.stage['primerStallSeconds'], completed=self.checkpoint())
        work_until = time.monotonic() + timeout if timeout is not None else None
        with subprocess.Popen(argv, **options) as child:
            try:
                while True:
                    self.window.observe(self.checkpoint())
                    work_left = work_until - time.monotonic() if work_until is not None else float('inf')
                    if work_left <= 0:
                        raise subprocess.TimeoutExpired(argv, timeout)
                    stall_left = self.window.remaining()
                    if stall_left <= 0:
                        raise RuntimeError('M7_PRIMER_STALLED')
                    try:
                        code = child.wait(timeout=min(5, self.window.seconds/4, stall_left, work_left))
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except BaseException:
                # Give the attached Compose client time to forward TERM and
                # drain admitted tenants. The owner's work cutoff still wins.
                child.terminate()
                grace = min(5, max(0, work_until - time.monotonic())) if work_until is not None else 5
                try:
                    child.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                # Capture any final checkpoint drained under TERM without
                # replacing the original cancellation, cutoff or read failure.
                try:
                    self.checkpoint()
                except (OSError, RuntimeError):
                    pass
                raise
            self.checkpoint()
        return subprocess.CompletedProcess(argv, code)
