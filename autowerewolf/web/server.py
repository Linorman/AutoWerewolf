import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from autowerewolf.config.models import AgentModelConfig, ModelBackend, ModelConfig
from autowerewolf.config.performance import PerformanceConfig, VerbosityLevel
from autowerewolf.engine.roles import RoleSet
from autowerewolf.engine.state import GameConfig, RuleVariants
from autowerewolf.web.game_manager import GameManager, GameStatus

logger = logging.getLogger(__name__)

game_manager = GameManager()


class CreateGameRequest(BaseModel):
    role_set: str = Field(default="A", description="Role set: 'A' (Guard) or 'B' (Village Idiot)")
    seed: Optional[int] = Field(default=None, description="Random seed for reproducibility")
    model_name: str = Field(default="llama3", description="Model name to use")
    backend: str = Field(default="ollama", description="Model backend: 'ollama' or 'api'")
    api_base: Optional[str] = Field(default=None, description="API base URL")
    api_key: Optional[str] = Field(default=None, description="API key")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    human_seats: Optional[list[int]] = Field(default=None, description="Seat numbers for human players")


class JoinGameRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=32)
    seat_number: Optional[int] = Field(default=None, ge=1, le=12)


class ActionRequest(BaseModel):
    player_id: str
    action_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.player_connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket, player_id: Optional[str] = None):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        
        if player_id:
            self.player_connections[player_id] = websocket

    def disconnect(self, session_id: str, websocket: WebSocket, player_id: Optional[str] = None):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
        if player_id and player_id in self.player_connections:
            del self.player_connections[player_id]

    async def broadcast(self, session_id: str, message: dict[str, Any]):
        if session_id not in self.active_connections:
            return
        disconnected = []
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections[session_id].remove(conn)

    async def send_to_player(self, player_id: str, message: dict[str, Any]):
        if player_id in self.player_connections:
            try:
                await self.player_connections[player_id].send_json(message)
            except Exception:
                pass


connection_manager = ConnectionManager()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AutoWerewolf API",
        description="LLM-powered Werewolf game simulation API",
        version="0.1.0",
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/")
    async def root():
        return RedirectResponse(url="/ui")

    @app.get("/api")
    async def api_info():
        return {"message": "AutoWerewolf API", "version": "0.1.0"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.post("/api/games")
    async def create_game(request: CreateGameRequest):
        role_set = RoleSet.A if request.role_set.upper() == "A" else RoleSet.B
        
        game_config = GameConfig(
            role_set=role_set,
            random_seed=request.seed,
            rule_variants=RuleVariants(),
        )
        
        backend = ModelBackend.OLLAMA if request.backend.lower() == "ollama" else ModelBackend.API
        model_config = ModelConfig(
            backend=backend,
            model_name=request.model_name,
            api_base=request.api_base,
            api_key=request.api_key,
            temperature=request.temperature,
        )
        agent_config = AgentModelConfig(default=model_config)
        
        performance_config = PerformanceConfig(
            verbosity=VerbosityLevel.STANDARD,
        )
        
        session = await game_manager.create_session(
            config=game_config,
            agent_config=agent_config,
            performance_config=performance_config,
            human_seats=request.human_seats,
        )
        
        return {
            "session_id": session.session_id,
            "status": session.status.value,
        }

    @app.get("/api/games")
    async def list_games():
        sessions = await game_manager.list_sessions()
        return {"games": sessions}

    @app.get("/api/games/{session_id}")
    async def get_game(session_id: str):
        session = await game_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Game not found")
        return session.to_dict()

    @app.post("/api/games/{session_id}/join")
    async def join_game(session_id: str, request: JoinGameRequest):
        player = await game_manager.join_session(
            session_id=session_id,
            player_name=request.player_name,
            seat_number=request.seat_number,
        )
        if not player:
            raise HTTPException(status_code=400, detail="Cannot join game")
        
        await connection_manager.broadcast(session_id, {
            "type": "player_joined",
            "player_id": player.player_id,
            "player_name": player.player_name,
        })
        
        return {
            "player_id": player.player_id,
            "player_name": player.player_name,
        }

    @app.post("/api/games/{session_id}/start")
    async def start_game(session_id: str):
        success = await game_manager.start_game(session_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot start game")
        
        await connection_manager.broadcast(session_id, {
            "type": "game_started",
        })
        
        return {"status": "started"}

    @app.get("/api/games/{session_id}/state")
    async def get_game_state(session_id: str, player_id: Optional[str] = None):
        state = await game_manager.get_game_state(session_id, player_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return state

    @app.post("/api/games/{session_id}/action")
    async def submit_action(session_id: str, request: ActionRequest):
        success = await game_manager.submit_action(
            session_id=session_id,
            player_id=request.player_id,
            action_data={
                "type": request.action_type,
                **request.data,
            },
        )
        if not success:
            raise HTTPException(status_code=400, detail="Cannot submit action")
        return {"status": "accepted"}

    @app.delete("/api/games/{session_id}")
    async def delete_game(session_id: str):
        success = await game_manager.delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Game not found")
        return {"status": "deleted"}

    @app.websocket("/ws/games/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str, player_id: Optional[str] = None):
        session = await game_manager.get_session(session_id)
        if not session:
            await websocket.close(code=4004, reason="Game not found")
            return
        
        await connection_manager.connect(session_id, websocket, player_id)
        
        def on_event(event: dict[str, Any]) -> None:
            asyncio.create_task(connection_manager.broadcast(session_id, event))
        
        session.on_event = on_event
        
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "action" and player_id:
                    await game_manager.submit_action(
                        session_id=session_id,
                        player_id=player_id,
                        action_data=message.get("data", {}),
                    )
                elif message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            connection_manager.disconnect(session_id, websocket, player_id)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            connection_manager.disconnect(session_id, websocket, player_id)

    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        
        @app.get("/ui", response_class=HTMLResponse)
        async def serve_ui():
            index_path = static_path / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="UI not found")
    
    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
