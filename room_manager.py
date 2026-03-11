import time
from typing import Dict, Set, Optional
from fastapi import WebSocket
import asyncio
from collections import OrderedDict

class TTLCache:
    """Memory-efficient TTL cache with automatic cleanup"""
    def __init__(self, max_size: int = 10000, default_ttl: int = 1800):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
    
    def set(self, key: str, value: any, ttl: Optional[int] = None):
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        
        self.cache[key] = {
            'value': value,
            'expires_at': time.time() + (ttl or self.default_ttl)
        }
        self.cache.move_to_end(key)
    
    def get(self, key: str) -> Optional[any]:
        if key not in self.cache:
            return None
        
        item = self.cache[key]
        if time.time() > item['expires_at']:
            del self.cache[key]
            return None
        
        self.cache.move_to_end(key)
        return item['value']
    
    def delete(self, key: str):
        if key in self.cache:
            del self.cache[key]
    
    def cleanup_expired(self):
        now = time.time()
        expired = [k for k, v in self.cache.items() if now > v['expires_at']]
        for key in expired:
            del self.cache[key]
        return len(expired)

class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Dict] = {}
        self.room_cache = TTLCache(max_size=10000, default_ttl=1800)
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_rooms())
        self.active_transfers: Dict[str, int] = {}
    
    def create_room(self, room_id: str, settings: dict = None):
        room_data = {
            "clients": {},
            "created_at": time.time(),
            "settings": settings or {},
            "failed_attempts": [],
            "transfer_active": False
        }
        self.rooms[room_id] = room_data
        self.room_cache.set(room_id, room_data)
    
    def room_exists(self, room_id: str) -> bool:
        return room_id in self.rooms
    
    def add_client(self, room_id: str, client_id: str, websocket: WebSocket):
        if room_id in self.rooms:
            self.rooms[room_id]["clients"][client_id] = websocket
    
    def remove_client(self, room_id: str, client_id: str):
        if room_id in self.rooms and client_id in self.rooms[room_id]["clients"]:
            del self.rooms[room_id]["clients"][client_id]
            if not self.rooms[room_id]["clients"]:
                del self.rooms[room_id]
    
    async def broadcast(self, room_id: str, message: dict, exclude: str = None):
        if room_id not in self.rooms:
            return
        
        tasks = []
        for client_id, ws in self.rooms[room_id]["clients"].items():
            if client_id != exclude:
                tasks.append(self._safe_send(ws, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception as e:
            pass
    
    async def send_to_client(self, room_id: str, client_id: str, message: dict):
        if room_id in self.rooms and client_id in self.rooms[room_id]["clients"]:
            try:
                await self.rooms[room_id]["clients"][client_id].send_json(message)
            except:
                pass
    
    async def handle_message(self, room_id: str, sender_id: str, data: dict):
        msg_type = data.get("type")
        target = data.get("target")
        
        # Add sender to message
        message_with_sender = {
            **data,
            "sender": sender_id
        }
        
        if msg_type in ["offer", "answer", "ice-candidate", "candidate"]:
            if target:
                # Send to specific target
                await self.send_to_client(room_id, target, message_with_sender)
            else:
                # Broadcast to all except sender
                await self.broadcast(room_id, message_with_sender, exclude=sender_id)
        else:
            # Handle other message types
            await self.broadcast(room_id, message_with_sender, exclude=sender_id)
    
    def add_failed_attempt(self, room_id: str, ip: str, user_agent: str):
        if room_id in self.rooms:
            self.rooms[room_id]["failed_attempts"].append({
                "ip": ip,
                "user_agent": user_agent,
                "timestamp": time.time()
            })
            return len(self.rooms[room_id]["failed_attempts"])
        return 0
    
    def get_failed_attempts(self, room_id: str):
        if room_id in self.rooms:
            return self.rooms[room_id].get("failed_attempts", [])
        return []
    
    def get_room_settings(self, room_id: str):
        if room_id in self.rooms:
            return self.rooms[room_id].get("settings", {})
        return None
    
    def get_room_info(self, room_id: str):
        """Get room information including client count and creation time"""
        if room_id in self.rooms:
            return self.rooms[room_id]
        return None
    
    async def _cleanup_expired_rooms(self):
        while True:
            await asyncio.sleep(60)
            current_time = time.time()
            
            # Cleanup rooms
            expired = [
                room_id for room_id, room in self.rooms.items()
                if current_time - room["created_at"] > 1800 and not room.get("transfer_active")
            ]
            for room_id in expired:
                await self._close_room(room_id)
            
            # Cleanup cache
            cleaned = self.room_cache.cleanup_expired()
            if cleaned > 0:
                print(f"[Cleanup] Removed {cleaned} expired cache entries")
    
    async def _close_room(self, room_id: str):
        if room_id in self.rooms:
            for ws in self.rooms[room_id]["clients"].values():
                try:
                    await ws.close()
                except:
                    pass
            del self.rooms[room_id]
            self.room_cache.delete(room_id)
