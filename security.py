import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_requests: int = 100, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)
    
    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self.requests[ip] = [req for req in self.requests[ip] if now - req < self.window]
        
        if len(self.requests[ip]) >= self.max_requests:
            return False
        
        self.requests[ip].append(now)
        return True
