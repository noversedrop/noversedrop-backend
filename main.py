from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
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

@app.middleware("http")
async def add_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Powered-By"] = "NoverseDrop"
    response.headers["X-Server-Time"] = str(int(time.time()))
    return response

@app.get("/api/create-room")
async def create_room():
    room_id = secrets.token_urlsafe(8)
    room_manager.create_room(room_id)
    return {"room_id": room_id}

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
