import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from autowerewolf.web.i18n import get_all_translations
from autowerewolf.web.schemas import (
    ActionResponse,
    ActionSubmitRequest,
    CreateGameRequest,
    EventResponse,
    GameListResponse,
    GameStateResponse,
    WSMessage,
    WSMessageType,
)
from autowerewolf.web.session import session_manager
from autowerewolf.web.config_loader import web_config_loader

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, game_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            if game_id not in self._connections:
                self._connections[game_id] = set()
            self._connections[game_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, game_id: str) -> None:
        async with self._lock:
            if game_id in self._connections:
                self._connections[game_id].discard(websocket)
                if not self._connections[game_id]:
                    del self._connections[game_id]

    async def broadcast(self, game_id: str, message: WSMessage) -> None:
        async with self._lock:
            connections = self._connections.get(game_id, set()).copy()
        
        data = message.model_dump()
        data["timestamp"] = datetime.now().isoformat()
        
        for websocket in connections:
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.error(f"WebSocket send error: {e}")

    async def send_to(self, websocket: WebSocket, message: WSMessage) -> None:
        data = message.model_dump()
        data["timestamp"] = datetime.now().isoformat()
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")


ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)
    yield
    for game_id in list(session_manager._sessions.keys()):
        session_manager.remove_session(game_id)


app = FastAPI(
    title="AutoWerewolf WebUI",
    description="Web interface for AutoWerewolf LLM-powered Werewolf game",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/config/ports")
async def get_ports():
    """Get the configured API and frontend ports."""
    api_port = getattr(app.state, "api_port", 8000)
    frontend_port = getattr(app.state, "frontend_port", 3000)
    return {"api_port": api_port, "frontend_port": frontend_port}


@app.get("/api/defaults")
async def get_defaults():
    """Get default configurations loaded from config files or built-in defaults."""
    return web_config_loader.get_defaults_dict()


@app.get("/api/translations/{language}")
async def get_translations(language: str = "en"):
    if language not in ("en", "zh"):
        language = "en"
    translations = get_all_translations(language)
    return {"language": language, "translations": translations}


@app.post("/api/games", response_model=GameStateResponse)
async def create_game(request: CreateGameRequest):
    try:
        session = session_manager.create_session(request)
        session.start()
        
        await asyncio.sleep(0.5)
        
        state = session.get_state_response()
        if state is None:
            return GameStateResponse(
                game_id=session.game_id,
                status=session.status,
                day_number=0,
                phase="night",
                players=[],
                sheriff_id=None,
                badge_torn=False,
                winning_team=None,
            )
        return state
    except Exception as e:
        logger.error(f"Create game error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/games", response_model=GameListResponse)
async def list_games():
    games = session_manager.list_sessions()
    return GameListResponse(games=games)


@app.get("/api/games/{game_id}", response_model=GameStateResponse)
async def get_game(game_id: str):
    session = session_manager.get_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")
    
    state = session.get_state_response()
    if state is None:
        return GameStateResponse(
            game_id=game_id,
            status=session.status,
            day_number=0,
            phase="unknown",
            players=[],
        )
    return state


@app.delete("/api/games/{game_id}")
async def stop_game(game_id: str):
    session = session_manager.get_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")
    
    session.stop()
    return {"success": True, "message": "Game stopped"}


@app.get("/api/games/{game_id}/players/{player_id}")
async def get_player_view(game_id: str, player_id: str):
    session = session_manager.get_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")
    
    view = session.get_player_view(player_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Player not found")
    
    return view


@app.get("/api/games/{game_id}/events", response_model=List[EventResponse])
async def get_events(game_id: str, start: int = 0):
    session = session_manager.get_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return session.get_events(start)


@app.post("/api/games/{game_id}/action", response_model=ActionResponse)
async def submit_action(game_id: str, action: ActionSubmitRequest):
    session = session_manager.get_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Game not found")
    
    result = session.submit_action(action)
    return ActionResponse(**result)


@app.websocket("/ws/game/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    session = session_manager.get_session(game_id)
    if session is None:
        await websocket.close(code=4004, reason="Game not found")
        return
    
    await ws_manager.connect(websocket, game_id)
    
    try:
        await ws_manager.send_to(websocket, WSMessage(
            type=WSMessageType.CONNECTED,
            data={"game_id": game_id, "status": session.status},
        ))
        
        state = session.get_state_response()
        if state:
            await ws_manager.send_to(websocket, WSMessage(
                type=WSMessageType.GAME_STATE,
                data=state.model_dump(),
            ))
        
        existing_events = session.get_events(0)
        for event in existing_events:
            await ws_manager.send_to(websocket, WSMessage(
                type=WSMessageType.EVENT,
                data=event.model_dump(),
            ))
        
        while True:
            receive_task = asyncio.create_task(
                asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            )
            
            try:
                data = await receive_task
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "action":
                        action_data = msg.get("data", {})
                        action = ActionSubmitRequest(**action_data)
                        result = session.submit_action(action)
                        await ws_manager.send_to(websocket, WSMessage(
                            type=WSMessageType.ACTION_RESPONSE,
                            data=result,
                        ))
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass
            
            realtime_event = session.get_realtime_event(timeout=0.05)
            while realtime_event:
                event_type = realtime_event.get("type")
                
                if event_type == "event":
                    event_data = realtime_event.get("event")
                    state_data = realtime_event.get("state")
                    
                    if event_data:
                        await ws_manager.send_to(websocket, WSMessage(
                            type=WSMessageType.EVENT,
                            data=event_data.model_dump() if hasattr(event_data, "model_dump") else event_data,
                        ))
                    
                    if state_data:
                        await ws_manager.send_to(websocket, WSMessage(
                            type=WSMessageType.GAME_STATE,
                            data=state_data,
                        ))
                
                elif event_type == "narration":
                    content = realtime_event.get("content", "")
                    await ws_manager.send_to(websocket, WSMessage(
                        type=WSMessageType.NARRATION,
                        data={"content": content},
                    ))
                
                elif event_type == "game_over":
                    winning_team = realtime_event.get("winning_team", "unknown")
                    await ws_manager.send_to(websocket, WSMessage(
                        type=WSMessageType.GAME_OVER,
                        data={"winning_team": winning_team},
                    ))
                    
                    state = session.get_state_response()
                    if state:
                        await ws_manager.send_to(websocket, WSMessage(
                            type=WSMessageType.GAME_STATE,
                            data=state.model_dump(),
                        ))
                
                elif event_type == "game_stopped":
                    message = realtime_event.get("message", "Game stopped")
                    await ws_manager.send_to(websocket, WSMessage(
                        type=WSMessageType.GAME_STOPPED,
                        data={"message": message},
                    ))
                    
                    state = session.get_state_response()
                    if state:
                        await ws_manager.send_to(websocket, WSMessage(
                            type=WSMessageType.GAME_STATE,
                            data=state.model_dump(),
                        ))
                
                elif event_type == "error":
                    message = realtime_event.get("message", "Unknown error")
                    await ws_manager.send_to(websocket, WSMessage(
                        type=WSMessageType.ERROR,
                        data={"message": message},
                    ))
                
                realtime_event = session.get_realtime_event(timeout=0.01)
            
            if session.status in ("completed", "error", "stopped"):
                await asyncio.sleep(0.5)
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for game {game_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await ws_manager.disconnect(websocket, game_id)


@app.get("/favicon.ico")
async def favicon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="45" fill="#0d0d14"/>
    <path d="M50 15c-19 0-35 16-35 35 0 13 7 24 17 30v-13c-4-4-7-10-7-17 0-14 11-25 25-25s25 11 25 25c0 7-3 13-7 17v13c10-6 17-17 17-30 0-19-16-35-35-35z" fill="#c9485b"/>
    <circle cx="38" cy="47" r="4" fill="#c9485b"/><circle cx="62" cy="47" r="4" fill="#c9485b"/>
    <path d="M38 60c0 0 6 8 12 8s12-8 12-8" stroke="#c9485b" stroke-width="2" fill="none"/>
    </svg>'''
    return HTMLResponse(content=svg, media_type="image/svg+xml")


frontend_app = FastAPI(
    title="AutoWerewolf Frontend",
    description="Frontend for AutoWerewolf",
    version="0.1.0",
)

frontend_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@frontend_app.get("/favicon.ico")
async def frontend_favicon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="45" fill="#0d0d14"/>
    <path d="M50 15c-19 0-35 16-35 35 0 13 7 24 17 30v-13c-4-4-7-10-7-17 0-14 11-25 25-25s25 11 25 25c0 7-3 13-7 17v13c10-6 17-17 17-30 0-19-16-35-35-35z" fill="#c9485b"/>
    <circle cx="38" cy="47" r="4" fill="#c9485b"/><circle cx="62" cy="47" r="4" fill="#c9485b"/>
    <path d="M38 60c0 0 6 8 12 8s12-8 12-8" stroke="#c9485b" stroke-width="2" fill="none"/>
    </svg>'''
    return HTMLResponse(content=svg, media_type="image/svg+xml")


@frontend_app.get("/")
async def frontend_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@frontend_app.get("/{path:path}")
async def frontend_path(request: Request, path: str):
    return templates.TemplateResponse("index.html", {"request": request})


def run_server(
    host: str = "0.0.0.0", 
    api_port: int = 8000,
    frontend_port: int = 3000,
    model_config_path: Optional[str] = None,
    game_config_path: Optional[str] = None,
) -> None:
    """
    Start the web server with optional configuration files.
    
    Args:
        host: Host to bind to.
        api_port: Port for API server.
        frontend_port: Port for frontend server.
        model_config_path: Path to model config YAML file. If None, searches default paths.
        game_config_path: Path to game config YAML file. If None, searches default paths.
    """
    import uvicorn
    import threading
    
    # Load configurations before starting server
    web_config_loader.load_from_file(model_config_path)
    web_config_loader.load_game_config(game_config_path)
    
    app.state.api_port = api_port
    app.state.frontend_port = frontend_port
    
    def run_frontend():
        uvicorn.run(frontend_app, host=host, port=frontend_port, log_level="info")
    
    # Start frontend server in a separate thread
    frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    frontend_thread.start()
    
    logger.info(f"Frontend server started on http://{host}:{frontend_port}")
    logger.info(f"API server starting on http://{host}:{api_port}")
    
    # Run API server in main thread
    uvicorn.run(app, host=host, port=api_port, log_level="info")
