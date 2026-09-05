"""
Supervisor: starts the bot and the scraper and keeps them running.

    python run.py            start both (normal use)
    python run.py bot        start only the Discord bot
    python run.py scraper    start only the scraper

A worker that crashes is restarted automatically. As a safety net, every worker
is also restarted once its runtime reaches MAX_RUNTIME_SECONDS, which clears out
any state a long-running process may have got stuck in.

Press Ctrl+C to stop everything.
"""

import logging
import subprocess
import sys
import time

import config

log = logging.getLogger("run")

WORKERS = {
    "bot": "bot.py",
    "scraper": "scraper.py",
}


class Worker:
    """One managed child process."""

    def __init__(self, name, script):
        self.name = name
        self.script = script
        self.process = None
        self.started_at = 0.0

    def start(self):
        """Launch the script. Output goes straight to this console."""
        self.process = subprocess.Popen(
            [sys.executable, "-u", self.script],
            cwd=str(config.BASE_DIR),
        )
        self.started_at = time.time()
        log.info("Started %s (pid %s)", self.name, self.process.pid)

    def stop(self):
        """Ask the process to close, then force it if it ignores us."""
        if self.process is None or self.process.poll() is not None:
            return

        log.info("Stopping %s (pid %s)", self.name, self.process.pid)
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log.warning("%s did not stop in time, killing it", self.name)
            self.process.kill()
            self.process.wait()

    @property
    def runtime(self):
        """How many seconds this process has been running."""
        return time.time() - self.started_at

    def check(self):
        """Restart the process if it died or has been running too long."""
        exit_code = self.process.poll()

        if exit_code is not None:
            log.warning("%s stopped with exit code %s, restarting", self.name, exit_code)
        elif self.runtime >= config.MAX_RUNTIME_SECONDS:
            log.info("%s reached its runtime limit, restarting", self.name)
            self.stop()
        else:
            return  # still healthy

        time.sleep(config.RESTART_DELAY_SECONDS)
        self.start()


def main():
    config.setup_logging("run")

    requested = sys.argv[1:] or list(WORKERS)
    unknown = [name for name in requested if name not in WORKERS]
    if unknown:
        log.error("Unknown worker(s): %s. Choose from: %s", ", ".join(unknown), ", ".join(WORKERS))
        return 1

    workers = [Worker(name, WORKERS[name]) for name in requested]

    for worker in workers:
        worker.start()

    try:
        while True:
            time.sleep(config.HEALTH_CHECK_INTERVAL)
            for worker in workers:
                worker.check()
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        for worker in workers:
            worker.stop()

    log.info("All workers stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
