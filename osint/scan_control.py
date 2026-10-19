"""Thread-safe GUI control over bounded asynchronous scan jobs."""
import asyncio
import threading
import time


class ScanStopped(Exception):
    pass


class ScanControl:
    def __init__(self):
        self.stopped = threading.Event()
        self.paused = threading.Event()
        self._lock = threading.Lock()
        self._jobs = {}
        self.started = time.monotonic()
        self.finished = None

    def finish(self):
        self.finished = time.monotonic()
        self.paused.clear()

    def register(self, keys):
        with self._lock:
            for key in keys:
                self._jobs.setdefault(key, {'state': 'waiting', 'started': None})

    def snapshot(self):
        now = time.monotonic()
        with self._lock:
            jobs = [{**v, 'name': k, 'seconds': round((v.get('finished') or now) - v['started'], 1) if v['started'] else 0}
                    for k, v in self._jobs.items()]
        return {'elapsed': round((self.finished or now) - self.started, 1), 'paused': self.paused.is_set(),
                'stopped': self.stopped.is_set(), 'jobs': jobs}

    async def run(self, key, factory, semaphore=None):
        self.register([key])
        acquired = False
        task = None
        try:
            while True:
                if self.stopped.is_set():
                    raise ScanStopped()
                if not self.paused.is_set():
                    if semaphore is None:
                        break
                    try:
                        await asyncio.wait_for(semaphore.acquire(), .1)
                        acquired = True
                        if not self.paused.is_set():
                            break
                        semaphore.release()
                        acquired = False
                    except asyncio.TimeoutError:
                        pass
                await asyncio.sleep(.05)
            with self._lock:
                self._jobs[key] = {'state': 'running', 'started': time.monotonic()}
            task = asyncio.create_task(factory())
            while not task.done():
                if self.stopped.is_set():
                    raise ScanStopped()
                await asyncio.wait({task}, timeout=.1)
            return await task
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if acquired:
                semaphore.release()
            with self._lock:
                self._jobs[key]['state'] = 'stopped' if self.stopped.is_set() else 'done'
                self._jobs[key]['finished'] = time.monotonic()


def interrupted_result(platform, *, email=False):
    return {'service' if email else 'platform': platform.get('name', 'Unknown'),
            'status': 'UNKNOWN' if email else 'unknown', 'found': False,
            'url': platform.get('url', ''), 'detail': 'Kullanıcı tarafından durduruldu; yeniden denenebilir.',
            'unknown_cause': 'cancelled', 'diagnostic_cause': 'cancelled'}
