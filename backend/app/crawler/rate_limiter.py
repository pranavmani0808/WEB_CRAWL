import time
import asyncio
import threading

class RateLimiter:
    """
    Token bucket rate limiter that ensures smooth, steady request distribution.
    Prevents bursting by spacing out requests evenly over time.
    """

    def __init__(self, requests_per_second=1.0):
        self.requests_per_second = max(0.01, requests_per_second)
        self.min_interval = 1.0 / self.requests_per_second
        self.last_request_time = 0.0
        self.lock = threading.Lock()

    def acquire(self):
        """Acquire permission (blocking sync version)"""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time

            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                time.sleep(sleep_time)
                self.last_request_time = time.time()
            else:
                self.last_request_time = now

    async def acquire_async(self):
        """Acquire permission (non-blocking async version)"""
        # Using a simple async lock
        # Since we run in async context, let's use time.time() and asyncio.sleep
        now = time.time()
        # We don't necessarily need a lock if single-threaded event loop, but good to keep it clean
        # Let's do simple calculation:
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            await asyncio.sleep(sleep_time)
            self.last_request_time = time.time()
        else:
            self.last_request_time = now

    def update_rate(self, requests_per_second):
        """Update the rate limit dynamically"""
        with self.lock:
            self.requests_per_second = max(0.01, requests_per_second)
            self.min_interval = 1.0 / self.requests_per_second
