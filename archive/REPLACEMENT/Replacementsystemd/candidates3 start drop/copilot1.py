#!/usr/bin/env python3

import os
import sqlite3
import threading
import queue
import sched
import signal
import time
import logging

try:
    from systemd import daemon
except ImportError:
    daemon = None

class ZombieReaper(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._q = queue.Queue()
        self.start()

    def run(self):
        while True:
            pid = self._q.get()
            if pid is None:
                break
            os.waitpid(pid, 0)

    def reap(self, pid):
        self._q.put(pid)

    def close(self):
        self._q.put(None)
        self.join()

class WorkflowManager:
    def __init__(self, db_path='/var/lib/aios/aios.db'):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()
        self.reaper = ZombieReaper()
        self.scheduler = sched.scheduler(time.time, time.sleep)
        signal.signal(signal.SIGCHLD, self._on_sigchld)

    def _init_db(self):
        cur = self.db.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY,
                command TEXT NOT NULL,
                delay INTEGER NOT NULL,
                realtime INTEGER NOT NULL DEFAULT 0
            )
        ''')
        self.db.commit()

    def _on_sigchld(self, *_):
        try:
            while True:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                self.reaper.reap(pid)
        except ChildProcessError:
            pass

    def add_workflow(self, cmd, delay, realtime=False):
        cur = self.db.cursor()
        cur.execute(
            'INSERT INTO workflows (command, delay, realtime) VALUES (?, ?, ?)',
            (cmd, delay, int(bool(realtime)))
        )
        self.db.commit()

    def load_and_schedule(self):
        now = time.time()
        cur = self.db.cursor()
        cur.execute('SELECT id, command, delay, realtime FROM workflows')
        for wf_id, cmd, delay, rt in cur:
            self.scheduler.enterabs(
                now + delay,
                1,
                self._execute,
                (wf_id, cmd, rt)
            )

    def _execute(self, wf_id, cmd, realtime):
        pid = os.fork()
        if pid == 0:
            if realtime:
                try:
                    os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(1))
                except PermissionError:
                    pass
            os.execvp(cmd.split()[0], cmd.split())
        else:
            self.reaper.reap(pid)
            cur = self.db.cursor()
            cur.execute('DELETE FROM workflows WHERE id = ?', (wf_id,))
            self.db.commit()

    def serve(self):
        if daemon:
            daemon.notify('READY=1')
        self.load_and_schedule()
        try:
            self.scheduler.run()
        except KeyboardInterrupt:
            pass
        finally:
            self.reaper.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    mgr = WorkflowManager()
    # Example: mgr.add_workflow('python3 /usr/bin/cleanup.py', delay=60, realtime=True)
    mgr.serve()
