import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from autowerewolf.web.i18n import get_all_translations, get_translation
from autowerewolf.web.schemas import (
    ActionResponse,
    ActionSubmitRequest,
    CreateGameRequest,
    EventResponse,
    GameListResponse,
    GameStateResponse,
    LanguageRequest,
    PlayerViewResponse,
    TranslationsResponse,
    WSMessage,
    WSMessageType,
)
from autowerewolf.web.session import GameSession, session_manager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


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


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/translations/{language}", response_model=TranslationsResponse)
async def get_translations(language: str = "en"):
    if language not in ("en", "zh"):
        language = "en"
    translations = get_all_translations(language)
    return TranslationsResponse(language=language, translations=translations)


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


@app.get("/api/games/{game_id}/players/{player_id}", response_model=PlayerViewResponse)
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
    <circle cx="50" cy="50" r="45" fill="#1a1a2e"/>
    <path d="M50 15c-19 0-35 16-35 35 0 13 7 24 17 30v-13c-4-4-7-10-7-17 0-14 11-25 25-25s25 11 25 25c0 7-3 13-7 17v13c10-6 17-17 17-30 0-19-16-35-35-35z" fill="#e94560"/>
    <circle cx="38" cy="47" r="4" fill="#e94560"/><circle cx="62" cy="47" r="4" fill="#e94560"/>
    <path d="M38 60c0 0 6 8 12 8s12-8 12-8" stroke="#e94560" stroke-width="2" fill="none"/>
    </svg>'''
    return HTMLResponse(content=svg, media_type="image/svg+xml")


@app.get("/ui")
async def serve_ui():
    return HTMLResponse(content=get_html_content(), status_code=200)


@app.get("/ui/{path:path}")
async def serve_ui_path(path: str):
    return HTMLResponse(content=get_html_content(), status_code=200)


def get_html_content() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoWerewolf</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid #333; margin-bottom: 20px; }
        .logo { font-size: 28px; font-weight: bold; color: #e94560; display: flex; align-items: center; gap: 10px; }
        .logo svg { width: 40px; height: 40px; }
        .header-controls { display: flex; gap: 15px; align-items: center; }
        select, input, button { padding: 10px 15px; border-radius: 8px; border: 1px solid #333; background: #16213e; color: #eee; font-size: 14px; }
        select:focus, input:focus { outline: none; border-color: #e94560; }
        button { cursor: pointer; background: #e94560; border: none; font-weight: 600; transition: all 0.2s; }
        button:hover { background: #ff6b6b; transform: translateY(-1px); }
        button:disabled { background: #444; cursor: not-allowed; transform: none; }
        button.secondary { background: #16213e; border: 1px solid #333; }
        button.secondary:hover { background: #1f3460; }
        .main-content { display: grid; grid-template-columns: 300px 1fr 350px; gap: 20px; min-height: calc(100vh - 150px); }
        .panel { background: #16213e; border-radius: 12px; padding: 20px; }
        .panel-title { font-size: 18px; font-weight: 600; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        .config-section { margin-bottom: 20px; }
        .config-section h3 { font-size: 14px; color: #888; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-size: 13px; color: #aaa; }
        .form-group input, .form-group select { width: 100%; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .player-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
        .player-card { background: #1a1a2e; border-radius: 8px; padding: 15px; text-align: center; transition: all 0.2s; border: 2px solid transparent; }
        .player-card.alive { border-color: #333; }
        .player-card.dead { opacity: 0.5; border-color: #ff4444; }
        .player-card.sheriff { border-color: #ffd700; }
        .player-card.werewolf { border-color: #e94560; }
        .player-card.special { border-color: #4ecdc4; }
        .player-seat { font-size: 12px; color: #666; margin-bottom: 5px; }
        .player-name { font-weight: 600; margin-bottom: 5px; }
        .player-role { font-size: 12px; padding: 3px 8px; border-radius: 4px; background: #333; display: inline-block; }
        .player-role.werewolf { background: #e94560; }
        .player-role.seer, .player-role.witch, .player-role.hunter, .player-role.guard { background: #4ecdc4; color: #000; }
        .player-role.village_idiot { background: #ffd700; color: #000; }
        .player-status { font-size: 11px; margin-top: 5px; color: #666; }
        .game-info { display: flex; justify-content: center; gap: 40px; margin-bottom: 20px; background: #1a1a2e; padding: 15px; border-radius: 8px; }
        .info-item { text-align: center; }
        .info-label { font-size: 12px; color: #666; text-transform: uppercase; }
        .info-value { font-size: 24px; font-weight: bold; color: #e94560; }
        .event-log { max-height: 500px; overflow-y: auto; }
        .event-item { padding: 12px; margin-bottom: 8px; background: #1a1a2e; border-radius: 8px; font-size: 13px; border-left: 4px solid #333; }
        .event-item.speech { border-color: #4ecdc4; background: linear-gradient(90deg, rgba(78,205,196,0.1) 0%, transparent 100%); }
        .event-item.death { border-color: #e94560; background: linear-gradient(90deg, rgba(233,69,96,0.1) 0%, transparent 100%); }
        .event-item.vote { border-color: #ffd700; background: linear-gradient(90deg, rgba(255,215,0,0.1) 0%, transparent 100%); }
        .event-item.sheriff { border-color: #9b59b6; background: linear-gradient(90deg, rgba(155,89,182,0.1) 0%, transparent 100%); }
        .event-item.system { border-color: #3498db; background: linear-gradient(90deg, rgba(52,152,219,0.1) 0%, transparent 100%); }
        .event-item.narration { border-color: #95a5a6; background: linear-gradient(90deg, rgba(149,165,166,0.15) 0%, transparent 100%); font-style: italic; }
        .event-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .event-time { font-size: 11px; color: #888; font-weight: 500; }
        .event-type-badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; background: #333; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; }
        .event-type-badge.speech { background: #4ecdc4; color: #000; }
        .event-type-badge.death { background: #e94560; color: #fff; }
        .event-type-badge.vote { background: #ffd700; color: #000; }
        .event-type-badge.sheriff { background: #9b59b6; color: #fff; }
        .event-type-badge.system { background: #3498db; color: #fff; }
        .event-type-badge.narration { background: #95a5a6; color: #fff; }
        .event-content { line-height: 1.5; word-break: break-word; }
        .event-content .speaker { color: #4ecdc4; font-weight: 600; }
        .event-content .target { color: #e94560; font-weight: 600; }
        .event-content .highlight { color: #ffd700; font-weight: 600; }
        .day-divider { text-align: center; padding: 10px; margin: 15px 0; border-top: 1px dashed #333; border-bottom: 1px dashed #333; color: #888; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
        .phase-indicator { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px; }
        .phase-indicator.night { background: #2c3e50; color: #bdc3c7; }
        .phase-indicator.day { background: #f39c12; color: #000; }
        .status-badge { padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .status-badge.running { background: #27ae60; }
        .status-badge.completed { background: #3498db; }
        .status-badge.error { background: #e94560; }
        .status-badge.created { background: #f39c12; }
        .winner-banner { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.95); padding: 60px 80px; border-radius: 20px; text-align: center; z-index: 1000; animation: fadeIn 0.5s; }
        .winner-title { font-size: 48px; font-weight: bold; margin-bottom: 20px; }
        .winner-banner.village .winner-title { color: #4ecdc4; }
        .winner-banner.werewolf .winner-title { color: #e94560; }
        @keyframes fadeIn { from { opacity: 0; transform: translate(-50%, -50%) scale(0.8); } to { opacity: 1; transform: translate(-50%, -50%) scale(1); } }
        .mode-tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .mode-tab { flex: 1; padding: 15px; text-align: center; background: #1a1a2e; border-radius: 8px; cursor: pointer; border: 2px solid transparent; transition: all 0.2s; }
        .mode-tab.active { border-color: #e94560; background: #16213e; }
        .mode-tab:hover { background: #16213e; }
        .private-info { background: #1a1a2e; padding: 15px; border-radius: 8px; margin-top: 15px; }
        .private-info h4 { font-size: 14px; color: #e94560; margin-bottom: 10px; }
        .private-item { display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; }
        .action-panel { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #16213e; padding: 20px 30px; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); z-index: 100; min-width: 400px; }
        .action-title { font-size: 16px; font-weight: 600; margin-bottom: 15px; color: #e94560; }
        .action-targets { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
        .action-target { padding: 8px 15px; background: #1a1a2e; border-radius: 6px; cursor: pointer; border: 2px solid transparent; }
        .action-target:hover { border-color: #e94560; }
        .action-target.selected { border-color: #e94560; background: #e94560; }
        .speech-input { width: 100%; min-height: 80px; margin-bottom: 15px; resize: vertical; }
        .action-buttons { display: flex; gap: 10px; justify-content: flex-end; }
        .no-game { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 300px; color: #666; }
        .no-game svg { width: 80px; height: 80px; margin-bottom: 20px; opacity: 0.3; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1a1a2e; }
        ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #444; }
        @media (max-width: 1200px) { .main-content { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <svg viewBox="0 0 100 100" fill="currentColor"><path d="M50 10c-22 0-40 18-40 40 0 15 8 28 20 35v-15c-5-5-8-12-8-20 0-15.5 12.5-28 28-28s28 12.5 28 28c0 8-3 15-8 20v15c12-7 20-20 20-35 0-22-18-40-40-40z"/><circle cx="35" cy="45" r="5"/><circle cx="65" cy="45" r="5"/><path d="M35 65c0 0 7 10 15 10s15-10 15-10" stroke="currentColor" stroke-width="3" fill="none"/></svg>
                <span>AutoWerewolf</span>
            </div>
            <div class="header-controls">
                <select id="language-select">
                    <option value="en">English</option>
                    <option value="zh">中文</option>
                </select>
                <span class="status-badge" id="connection-status">Disconnected</span>
            </div>
        </header>

        <div class="mode-tabs">
            <div class="mode-tab active" data-mode="watch" id="watch-tab">
                <strong id="t-watch_mode">Watch Mode</strong>
                <p style="font-size: 12px; color: #666; margin-top: 5px;" id="t-watch_desc">Watch AI agents play</p>
            </div>
            <div class="mode-tab" data-mode="play" id="play-tab">
                <strong id="t-play_mode">Play Mode</strong>
                <p style="font-size: 12px; color: #666; margin-top: 5px;" id="t-play_desc">Join the game as a player</p>
            </div>
        </div>

        <div class="main-content">
            <div class="panel" id="config-panel">
                <div class="panel-title" id="t-game_config">Game Configuration</div>
                
                <div class="config-section">
                    <h3 id="t-model_config">Model Settings</h3>
                    <div class="form-group">
                        <label id="t-backend">Backend</label>
                        <select id="backend-select">
                            <option value="ollama">Ollama</option>
                            <option value="api">API</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label id="t-model_name">Model Name</label>
                        <input type="text" id="model-name" value="llama3">
                    </div>
                    <div class="form-group" id="api-base-group" style="display:none;">
                        <label id="t-api_base">API Base URL</label>
                        <input type="text" id="api-base" placeholder="https://api.openai.com/v1">
                    </div>
                    <div class="form-group" id="api-key-group" style="display:none;">
                        <label id="t-api_key">API Key</label>
                        <input type="password" id="api-key">
                    </div>
                    <div class="form-group" id="ollama-url-group">
                        <label id="t-ollama_url">Ollama URL</label>
                        <input type="text" id="ollama-url" placeholder="http://localhost:11434">
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label id="t-temperature">Temperature</label>
                            <input type="number" id="temperature" value="0.7" min="0" max="2" step="0.1">
                        </div>
                        <div class="form-group">
                            <label id="t-max_tokens">Max Tokens</label>
                            <input type="number" id="max-tokens" value="1024" min="100" max="4096">
                        </div>
                    </div>
                </div>

                <div class="config-section">
                    <h3 id="t-game_rules">Game Rules</h3>
                    <div class="form-group">
                        <label id="t-role_set">Role Set</label>
                        <select id="role-set">
                            <option value="A" id="t-role_set_a">Set A (Guard)</option>
                            <option value="B" id="t-role_set_b">Set B (Village Idiot)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label id="t-random_seed">Random Seed (optional)</label>
                        <input type="number" id="random-seed" placeholder="Leave empty for random">
                    </div>
                </div>

                <div class="config-section" id="play-config" style="display:none;">
                    <h3 id="t-player_settings">Player Settings</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label id="t-your_seat">Your Seat</label>
                            <select id="player-seat">
                                <option value="1">1</option><option value="2">2</option><option value="3">3</option>
                                <option value="4">4</option><option value="5">5</option><option value="6">6</option>
                                <option value="7">7</option><option value="8">8</option><option value="9">9</option>
                                <option value="10">10</option><option value="11">11</option><option value="12">12</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label id="t-your_name">Your Name</label>
                            <input type="text" id="player-name" value="Human Player">
                        </div>
                    </div>
                </div>

                <button id="start-btn" style="width: 100%; margin-top: 10px;" id="t-start_game">Start Game</button>
                <button id="stop-btn" class="secondary" style="width: 100%; margin-top: 10px; display: none;" id="t-stop_game">Stop Game</button>
            </div>

            <div class="panel" id="game-panel">
                <div class="panel-title">
                    <span id="t-players">Players</span>
                    <span class="status-badge" id="game-status">Not Started</span>
                </div>
                
                <div class="game-info" id="game-info" style="display: none;">
                    <div class="info-item">
                        <div class="info-label" id="t-day">Day</div>
                        <div class="info-value" id="day-number">0</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label" id="t-phase">Phase</div>
                        <div class="info-value" id="phase-name">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label" id="t-alive">Alive</div>
                        <div class="info-value" id="alive-count">12</div>
                    </div>
                </div>

                <div class="player-grid" id="player-grid">
                    <div class="no-game">
                        <svg viewBox="0 0 100 100" fill="currentColor"><path d="M50 10c-22 0-40 18-40 40 0 15 8 28 20 35v-15c-5-5-8-12-8-20 0-15.5 12.5-28 28-28s28 12.5 28 28c0 8-3 15-8 20v15c12-7 20-20 20-35 0-22-18-40-40-40z"/></svg>
                        <p id="t-no_game_running">No game running</p>
                    </div>
                </div>
            </div>

            <div class="panel" id="events-panel">
                <div class="panel-title" id="t-game_log">Game Progress</div>
                <div class="event-log" id="event-log">
                    <div class="no-game" style="height: 200px;">
                        <p id="t-events_appear">Events will appear here</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div id="winner-banner" class="winner-banner" style="display: none;">
        <div class="winner-title" id="winner-text"></div>
        <button onclick="closeWinnerBanner()">Close</button>
    </div>

    <div id="action-panel" class="action-panel" style="display: none;">
        <div class="action-title" id="action-title"></div>
        <div class="action-targets" id="action-targets"></div>
        <textarea class="speech-input" id="speech-input" style="display: none;" placeholder="Enter your speech..."></textarea>
        <div class="action-buttons">
            <button class="secondary" onclick="skipAction()" id="t-skip">Skip</button>
            <button onclick="submitAction()" id="t-submit">Submit</button>
        </div>
    </div>

    <script>
        const API_BASE = '/api';
        let currentGameId = null;
        let ws = null;
        let translations = {};
        let currentLanguage = 'en';
        let currentMode = 'watch';
        let selectedTarget = null;

        async function loadTranslations(lang) {
            try {
                const res = await fetch(`${API_BASE}/translations/${lang}`);
                const data = await res.json();
                translations = data.translations;
                currentLanguage = lang;
                applyTranslations();
            } catch (e) { console.error('Load translations error:', e); }
        }

        function t(key) { return translations[key] || key; }

        function applyTranslations() {
            document.querySelectorAll('[id^="t-"]').forEach(el => {
                const key = el.id.substring(2);
                if (translations[key]) {
                    if (el.tagName === 'INPUT') el.placeholder = translations[key];
                    else el.textContent = translations[key];
                }
            });
        }

        document.getElementById('language-select').addEventListener('change', (e) => {
            loadTranslations(e.target.value);
        });

        document.querySelectorAll('.mode-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentMode = tab.dataset.mode;
                document.getElementById('play-config').style.display = currentMode === 'play' ? 'block' : 'none';
            });
        });

        document.getElementById('backend-select').addEventListener('change', (e) => {
            const isApi = e.target.value === 'api';
            document.getElementById('api-base-group').style.display = isApi ? 'block' : 'none';
            document.getElementById('api-key-group').style.display = isApi ? 'block' : 'none';
            document.getElementById('ollama-url-group').style.display = isApi ? 'none' : 'block';
        });

        document.getElementById('start-btn').addEventListener('click', startGame);
        document.getElementById('stop-btn').addEventListener('click', stopGame);

        async function startGame() {
            const config = {
                mode: currentMode,
                model_config_data: {
                    backend: document.getElementById('backend-select').value,
                    model_name: document.getElementById('model-name').value,
                    api_base: document.getElementById('api-base').value || null,
                    api_key: document.getElementById('api-key').value || null,
                    ollama_base_url: document.getElementById('ollama-url').value || null,
                    temperature: parseFloat(document.getElementById('temperature').value),
                    max_tokens: parseInt(document.getElementById('max-tokens').value),
                },
                game_config: {
                    role_set: document.getElementById('role-set').value,
                    random_seed: document.getElementById('random-seed').value ? parseInt(document.getElementById('random-seed').value) : null,
                },
            };

            if (currentMode === 'play') {
                config.player_seat = parseInt(document.getElementById('player-seat').value);
                config.player_name = document.getElementById('player-name').value;
            }

            try {
                document.getElementById('start-btn').disabled = true;
                const res = await fetch(`${API_BASE}/games`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config),
                });
                const data = await res.json();
                currentGameId = data.game_id;
                connectWebSocket(currentGameId);
                document.getElementById('start-btn').style.display = 'none';
                document.getElementById('stop-btn').style.display = 'block';
                document.getElementById('game-info').style.display = 'flex';
                document.getElementById('event-log').innerHTML = '';
                lastDay = 0;
                lastPhase = '';
            } catch (e) {
                console.error('Start game error:', e);
                alert('Failed to start game: ' + e.message);
            } finally {
                document.getElementById('start-btn').disabled = false;
            }
        }

        async function stopGame() {
            if (!currentGameId) return;
            try {
                await fetch(`${API_BASE}/games/${currentGameId}`, { method: 'DELETE' });
                if (ws) ws.close();
                currentGameId = null;
                document.getElementById('start-btn').style.display = 'block';
                document.getElementById('stop-btn').style.display = 'none';
            } catch (e) { console.error('Stop game error:', e); }
        }

        function connectWebSocket(gameId) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/game/${gameId}`);
            
            ws.onopen = () => {
                document.getElementById('connection-status').textContent = t('connected');
                document.getElementById('connection-status').className = 'status-badge running';
            };
            
            ws.onclose = () => {
                document.getElementById('connection-status').textContent = t('disconnected');
                document.getElementById('connection-status').className = 'status-badge error';
            };
            
            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                handleWSMessage(msg);
            };
        }

        function handleWSMessage(msg) {
            switch (msg.type) {
                case 'game_state':
                    updateGameState(msg.data);
                    break;
                case 'event':
                    addEvent(msg.data);
                    break;
                case 'narration':
                    addNarration(msg.data.content);
                    break;
                case 'game_over':
                    showWinner(msg.data.winning_team);
                    break;
                case 'action_request':
                    showActionPanel(msg.data);
                    break;
            }
        }

        function updateGameState(state) {
            document.getElementById('day-number').textContent = state.day_number;
            document.getElementById('phase-name').textContent = state.phase === 'night' ? t('night') : t('day');
            document.getElementById('game-status').textContent = state.status;
            document.getElementById('game-status').className = 'status-badge ' + state.status;
            
            const alivePlayers = state.players.filter(p => p.is_alive);
            document.getElementById('alive-count').textContent = alivePlayers.length;
            
            renderPlayers(state.players, state.sheriff_id);
        }

        function renderPlayers(players, sheriffId) {
            const grid = document.getElementById('player-grid');
            grid.innerHTML = '';
            
            players.forEach(player => {
                const card = document.createElement('div');
                let classes = ['player-card'];
                if (player.is_alive) classes.push('alive');
                else classes.push('dead');
                if (player.id === sheriffId) classes.push('sheriff');
                if (player.role === 'werewolf') classes.push('werewolf');
                else if (['seer', 'witch', 'hunter', 'guard', 'village_idiot'].includes(player.role)) classes.push('special');
                
                card.className = classes.join(' ');
                
                const roleClass = player.role !== 'hidden' ? player.role : '';
                const roleDisplay = player.role !== 'hidden' ? t(player.role) || player.role : '???';
                
                card.innerHTML = `
                    <div class="player-seat">${t('seat')} ${player.seat_number}</div>
                    <div class="player-name">${player.name}</div>
                    <div class="player-role ${roleClass}">${roleDisplay}</div>
                    <div class="player-status">${player.is_alive ? t('alive') : t('dead')}${player.id === sheriffId ? ' 👑' : ''}</div>
                `;
                
                grid.appendChild(card);
            });
        }

        let lastDay = 0;
        let lastPhase = '';

        function addEvent(event) {
            const log = document.getElementById('event-log');
            if (log.querySelector('.no-game')) log.innerHTML = '';
            
            if (event.day_number !== lastDay || event.phase !== lastPhase) {
                if (lastDay !== 0 || lastPhase !== '') {
                    const divider = document.createElement('div');
                    divider.className = 'day-divider';
                    const phaseText = event.phase === 'night' ? t('night') : t('day');
                    divider.innerHTML = `📅 ${t('day')} ${event.day_number} - ${phaseText}`;
                    log.appendChild(divider);
                }
                lastDay = event.day_number;
                lastPhase = event.phase;
            }
            
            const item = document.createElement('div');
            let eventClass = 'event-item';
            let typeBadge = 'system';
            let typeName = event.event_type;
            
            if (event.event_type === 'speech') {
                eventClass += ' speech';
                typeBadge = 'speech';
                typeName = event.data && event.data.is_last_words ? t('last_words') : t('speech');
            } else if (event.event_type.includes('death') || event.event_type === 'lynch' || event.event_type.includes('shot')) {
                eventClass += ' death';
                typeBadge = 'death';
                if (event.event_type === 'death_announcement') typeName = '💀 ' + t('dead');
                else if (event.event_type === 'lynch') typeName = '⚖️ Lynch';
                else if (event.event_type === 'hunter_shot') typeName = '🔫 Shot';
            } else if (event.event_type.includes('vote')) {
                eventClass += ' vote';
                typeBadge = 'vote';
                typeName = '🗳️ ' + t('vote');
            } else if (event.event_type.includes('sheriff') || event.event_type.includes('badge')) {
                eventClass += ' sheriff';
                typeBadge = 'sheriff';
                typeName = '👑 Sheriff';
            } else {
                eventClass += ' system';
            }
            
            item.className = eventClass;
            
            const phaseIndicator = event.phase === 'night' 
                ? `<span class="phase-indicator night">🌙</span>`
                : `<span class="phase-indicator day">☀️</span>`;
            
            item.innerHTML = `
                <div class="event-header">
                    <span class="event-type-badge ${typeBadge}">${typeName}</span>
                    <span class="event-time">${phaseIndicator}</span>
                </div>
                <div class="event-content">${formatEventContent(event)}</div>
            `;
            
            log.appendChild(item);
            log.scrollTop = log.scrollHeight;
        }
        
        function formatEventContent(event) {
            let content = event.description || event.event_type;
            
            if (event.actor_name) {
                content = content.replace(event.actor_name, `<span class="speaker">${event.actor_name}</span>`);
            }
            if (event.target_name && event.target_name !== event.actor_name) {
                content = content.replace(event.target_name, `<span class="target">${event.target_name}</span>`);
            }
            
            return content;
        }
        
        function addNarration(content) {
            const log = document.getElementById('event-log');
            if (log.querySelector('.no-game')) log.innerHTML = '';
            
            const item = document.createElement('div');
            item.className = 'event-item narration';
            item.innerHTML = `
                <div class="event-header">
                    <span class="event-type-badge narration">📢 Moderator</span>
                </div>
                <div class="event-content">${content}</div>
            `;
            
            log.appendChild(item);
            log.scrollTop = log.scrollHeight;
        }

        function showWinner(team) {
            const banner = document.getElementById('winner-banner');
            const text = document.getElementById('winner-text');
            banner.className = 'winner-banner ' + team;
            text.textContent = team === 'village' ? t('village_wins') : t('werewolf_wins');
            banner.style.display = 'block';
        }

        function closeWinnerBanner() {
            document.getElementById('winner-banner').style.display = 'none';
        }

        function showActionPanel(data) {
            const panel = document.getElementById('action-panel');
            document.getElementById('action-title').textContent = data.prompt || t('your_turn');
            
            const targets = document.getElementById('action-targets');
            targets.innerHTML = '';
            selectedTarget = null;
            
            if (data.valid_targets) {
                data.valid_targets.forEach(target => {
                    const btn = document.createElement('div');
                    btn.className = 'action-target';
                    btn.textContent = target;
                    btn.onclick = () => {
                        document.querySelectorAll('.action-target').forEach(t => t.classList.remove('selected'));
                        btn.classList.add('selected');
                        selectedTarget = target;
                    };
                    targets.appendChild(btn);
                });
            }
            
            const speechInput = document.getElementById('speech-input');
            speechInput.style.display = data.action_type === 'speech' ? 'block' : 'none';
            
            panel.style.display = 'block';
        }

        function submitAction() {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            
            const action = {
                type: 'action',
                data: {
                    action_type: 'submit',
                    target_id: selectedTarget,
                    content: document.getElementById('speech-input').value,
                }
            };
            
            ws.send(JSON.stringify(action));
            document.getElementById('action-panel').style.display = 'none';
            document.getElementById('speech-input').value = '';
        }

        function skipAction() {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            ws.send(JSON.stringify({ type: 'action', data: { action_type: 'skip' } }));
            document.getElementById('action-panel').style.display = 'none';
        }

        loadTranslations('en');
    </script>
</body>
</html>'''


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
