from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from room_manager import RoomManager
from security import RateLimiter
import secrets
import uvicorn
import time

app = FastAPI(title="NoverseDrop API", description="P2P File Transfer Signaling Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://noversedropshare.web.app",
        "https://noversedropshare.firebaseapp.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

room_manager = RoomManager()
rate_limiter = RateLimiter()

from typing import Optional

class RoomSettings(BaseModel):
    password: Optional[str] = None
    maxReceivers: Optional[int] = None

@app.middleware("http")
async def add_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Powered-By"] = "NoverseDrop"
    response.headers["X-Server-Time"] = str(int(time.time()))
    return response

@app.get("/")
async def root():
    return {
        "service": "NoverseDrop API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "create_room": "/api/create-room",
            "websocket": "/ws/{room_id}"
        }
    }

@app.get("/api/create-room")
async def create_room():
    room_id = secrets.token_urlsafe(8)
    room_manager.create_room(room_id)
    return {"room_id": room_id}

@app.post("/api/room/{room_id}/password-attempt")
async def check_password(room_id: str, request: Request, password: dict):
    settings = room_manager.get_room_settings(room_id)
    if not settings:
        return {"error": "Room not found"}
    
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "Unknown")
    
    if password.get("password") == settings.get("password"):
        return {"success": True}
    
    # Wrong password
    attempts = room_manager.add_failed_attempt(room_id, client_ip, user_agent)
    
    # Notify sender via WebSocket
    await room_manager.broadcast(room_id, {
        "type": "password-failed",
        "ip": client_ip,
        "user_agent": user_agent,
        "attempts": attempts
    })
    
    if attempts >= 4:
        return {"error": "Too many attempts", "blocked": True}
    
    return {"error": "Wrong password", "attempts": attempts}

@app.post("/api/room/{room_id}/settings")
async def save_room_settings(room_id: str, settings: RoomSettings):
    if room_manager.room_exists(room_id):
        room_manager.rooms[room_id]["settings"] = settings.dict()
        return {"success": True}
    return {"error": "Room not found"}

@app.get("/api/room/{room_id}/settings")
async def get_room_settings(room_id: str):
    settings = room_manager.get_room_settings(room_id)
    if settings is None:
        return {"error": "Room not found"}
    return {"settings": settings}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    client_id = secrets.token_urlsafe(6)
    
    if not room_manager.room_exists(room_id):
        room_manager.create_room(room_id)
    
    room_manager.add_client(room_id, client_id, websocket)
    
    await room_manager.broadcast(room_id, {
        "type": "peer-joined",
        "client_id": client_id
    }, exclude=client_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            await room_manager.handle_message(room_id, client_id, data)
    except WebSocketDisconnect:
        room_manager.remove_client(room_id, client_id)
        await room_manager.broadcast(room_id, {
            "type": "peer-left",
            "client_id": client_id
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
