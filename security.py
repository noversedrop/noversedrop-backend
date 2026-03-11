import time
from collections import defaultdict
from typing import Dict, List

class RateLimiter:
    def __init__(self, max_requests: int = 100, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.blocked_ips: Dict[str, float] = {}
        self.block_duration = 300  # 5 minutes
    
    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        
        # Check if IP is blocked
        if ip in self.blocked_ips:
            if now - self.blocked_ips[ip] < self.block_duration:
                return False
            else:
                del self.blocked_ips[ip]
        
        # Clean old requests
        self.requests[ip] = [req for req in self.requests[ip] if now - req < self.window]
        
        if len(self.requests[ip]) >= self.max_requests:
            self.blocked_ips[ip] = now
            return False
        
        self.requests[ip].append(now)
        return True
    
    def cleanup(self):
        """Remove old entries to prevent memory leak"""
        now = time.time()
        # Remove IPs with no recent requests
        self.requests = defaultdict(list, {
            ip: reqs for ip, reqs in self.requests.items()
            if reqs and now - reqs[-1] < self.window * 2
        })
        # Remove expired blocks
        self.blocked_ips = {
            ip: blocked_at for ip, blocked_at in self.blocked_ips.items()
            if now - blocked_at < self.block_duration
        }
