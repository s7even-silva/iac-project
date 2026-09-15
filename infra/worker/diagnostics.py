"""Bounded, best-effort Linux diagnostics; never attach/stop the simulation."""
import json
import os
from pathlib import Path
import time
import uuid


def read(path, limit=16384):
    try:
        with Path(path).open('rb') as stream:
            return stream.read(limit).decode(errors='replace')
    except OSError as exc:
        return {'unavailable': str(exc)}


class Sampler:
    def __init__(self, root_pid):
        self.root_pid = root_pid
        self.previous = {}
        self.history = []

    def sample(self):
        now = time.monotonic()
        processes = {}
        for path in Path('/proc').glob('[0-9]*/stat'):
            raw = read(path)
            if not isinstance(raw, str):
                continue
            fields = raw[raw.rfind(')') + 2:].split()
            if len(fields) >= 22:
                processes[int(path.parent.name)] = (int(fields[1]), path.parent)
        selected = {self.root_pid}
        while True:
            expanded = selected | {pid for pid, (parent, _) in processes.items() if parent in selected}
            if expanded == selected:
                break
            selected = expanded
        threads = []
        current = {}
        for pid in sorted(selected):
            for task in Path(f'/proc/{pid}/task').glob('[0-9]*'):
                raw = read(task / 'stat')
                if not isinstance(raw, str):
                    continue
                fields = raw[raw.rfind(')') + 2:].split()
                if len(fields) < 22:
                    continue
                key = (pid, int(task.name), fields[19])  # starttime prevents PID reuse
                ticks = int(fields[11]) + int(fields[12])
                old = self.previous.get(key)
                cpu = (100 * (ticks - old[1]) / os.sysconf('SC_CLK_TCK') / (now - old[0])) if old and now > old[0] else None
                threads.append(dict(pid=pid, tid=int(task.name), state=fields[0], cpu_pct_one_core=cpu,
                                    wchan=read(task / 'wchan', 256)))
                current[key] = (now, ticks)
        self.previous = current
        result = dict(monotonic=now, utc=time.time(), threads=threads,
                      processes={str(pid): {name: read(f'/proc/{pid}/{name}') for name in ('status', 'io', 'cgroup')} for pid in selected},
                      pressure={name: read('/proc/pressure/' + name) for name in ('cpu', 'memory', 'io')},
                      cgroup={name: read('/sys/fs/cgroup/' + name) for name in ('cpu.stat', 'cpu.max', 'memory.events', 'memory.current', 'memory.max', 'memory.swap.current')})
        self.history.append(result)
        self.history = self.history[-10:]
        return result

    def capture(self, destination, work, job, command, image):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        # At most three captures per attempt, preventing unbounded recurrent warnings.
        prefix = f"job-{job['job_id']}-attempt-{job.get('attempt', 0)}-"
        if len(list(destination.glob(prefix + '*.json'))) >= 3:
            return None
        sample = self.sample()
        stacks = {f"{t['pid']}/{t['tid']}": read(f"/proc/{t['pid']}/task/{t['tid']}/stack") for t in sample['threads']}
        artifacts = {}
        for pattern in ('generated_macros_organ/*.mac', '**/organ_run_*.mac', 'events/*.jsonl', 'logs_organ/*.log', 'worker_stdout.log'):
            for path in sorted(Path(work).glob(pattern))[:256]:
                # Tail logs, full bounded macro. Never read credentials/environment.
                try:
                    with path.open('rb') as stream:
                        if path.suffix != '.mac':
                            stream.seek(max(0, path.stat().st_size - 65536))
                        artifacts[str(path.relative_to(work))] = stream.read(65536).decode(errors='replace')
                except OSError:
                    pass
        pending = []
        for name, content in artifacts.items():
            if name.startswith('events/'):
                last = None
                for line in content.splitlines():
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict):
                            last = event
                    except ValueError:
                        pass  # a concurrent write or bounded tail may cut a line
                if last and last.get('phase') == 'begin':
                    pending.append(last)
        payload = dict(pending_events=pending, job=job, command=command, image_digest=image, samples=self.history,
                       kernel_stacks=stacks, artifacts=artifacts,
                       limitations='Kernel stacks may require permissions; no native user-space backtrace. CPU percent: 100 = one core. Artifacts bounded to 64 KiB each.')
        target = destination / (prefix + uuid.uuid4().hex + '.json')
        temporary = target.with_suffix('.tmp')
        with temporary.open('x') as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
        return target
