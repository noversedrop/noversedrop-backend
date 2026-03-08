import time
from typing import Dict, Set
from fastapi import WebSocket
import asyncio

class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Dict] = {}
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_rooms())
    
    def create_room(self, room_id: str):
        self.rooms[room_id] = {
            "clients": {},
            "created_at": time.time()
        }
    
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
        
        for client_id, ws in self.rooms[room_id]["clients"].items():
            if client_id != exclude:
                try:
                    await ws.send_json(message)
                except:
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
        
        if msg_type in ["offer", "answer", "ice-candidate"]:
            if target:
                await self.send_to_client(room_id, target, {
                    **data,
                    "sender": sender_id
                })
            else:
                await self.broadcast(room_id, {
                    **data,
                    "sender": sender_id
                }, exclude=sender_id)
    
    async def _cleanup_expired_rooms(self):
        while True:
            await asyncio.sleep(60)
            current_time = time.time()
            expired = [
                room_id for room_id, room in self.rooms.items()
                if current_time - room["created_at"] > 1800  # 30 minutes
            ]
            for room_id in expired:
                del self.rooms[room_id]
