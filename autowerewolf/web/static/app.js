const API_BASE = '';
let ws = null;
let currentSession = null;
let currentPlayerId = null;
let selectedTarget = null;
let currentGameMode = 'play'; // 'play' or 'watch'
let currentLang = localStorage.getItem('lang') || 'en';

// i18n translations
const translations = {
    en: {
        subtitle: 'LLM-powered Werewolf Game',
        createNewGame: 'Create New Game',
        gameMode: 'Game Mode',
        playWithAgents: 'Play with AI Agents',
        watchAgents: 'Watch AI Agents Play',
        playModeHint: 'You will join the game as a player alongside AI agents.',
        watchModeHint: 'You will watch AI agents play against each other.',
        selectSeat: 'Select Your Seat (Optional)',
        randomSeat: 'Random Seat',
        roleSet: 'Role Set',
        setAGuard: 'Set A (with Guard)',
        setBVillageIdiot: 'Set B (with Village Idiot)',
        model: 'Model',
        backend: 'Backend',
        ollamaLocal: 'Ollama (Local)',
        api: 'API',
        apiBaseUrl: 'API Base URL',
        apiKey: 'API Key',
        createGame: 'Create Game',
        activeGames: 'Active Games',
        noActiveGames: 'No active games',
        refresh: 'Refresh',
        waitingRoom: 'Waiting Room',
        session: 'Session',
        yourName: 'Your name',
        joinGame: 'Join Game',
        startGame: 'Start Game',
        leave: 'Leave',
        players: 'Players',
        selectAction: 'Select Action',
        submit: 'Submit',
        gameOver: 'Game Over',
        newGame: 'New Game',
        poweredBy: 'Powered by LLM Agents',
        dayN: 'Day {n}',
        night: 'Night',
        day: 'Day',
        join: 'Join',
        watch: 'Watch',
        playMode: '🎮 Play Mode',
        watchMode: '👁️ Watch Mode',
        villageWins: '🏘️ Village Wins!',
        werewolvesWin: '🐺 Werewolves Win!',
        villageWinMsg: 'The villagers successfully eliminated all werewolves!',
        werewolvesWinMsg: 'The werewolves have taken over the village!',
        playerJoined: '{name} joined the game',
        gameStarted: 'Game started!',
        foundDead: '{name} was found dead',
        votedFor: '{voter} voted for {target}',
        phaseBegins: '{phase} phase begins',
        error: 'Error',
        enterYourMessage: 'Enter your message...',
        youAre: 'You are: {role}',
        sheriff: 'Sheriff'
    },
    zh: {
        subtitle: 'LLM驱动的狼人杀游戏',
        createNewGame: '创建新游戏',
        gameMode: '游戏模式',
        playWithAgents: '与AI一起游戏',
        watchAgents: '观看AI对战',
        playModeHint: '你将作为玩家与AI一起参与游戏。',
        watchModeHint: '你将观看AI之间的对战。',
        selectSeat: '选择座位（可选）',
        randomSeat: '随机座位',
        roleSet: '角色配置',
        setAGuard: '配置A（含守卫）',
        setBVillageIdiot: '配置B（含白痴）',
        model: '模型',
        backend: '后端',
        ollamaLocal: 'Ollama（本地）',
        api: 'API',
        apiBaseUrl: 'API基础URL',
        apiKey: 'API密钥',
        createGame: '创建游戏',
        activeGames: '进行中的游戏',
        noActiveGames: '暂无进行中的游戏',
        refresh: '刷新',
        waitingRoom: '等候室',
        session: '会话',
        yourName: '你的名字',
        joinGame: '加入游戏',
        startGame: '开始游戏',
        leave: '离开',
        players: '玩家',
        selectAction: '选择行动',
        submit: '提交',
        gameOver: '游戏结束',
        newGame: '新游戏',
        poweredBy: '由LLM代理驱动',
        dayN: '第{n}天',
        night: '夜晚',
        day: '白天',
        join: '加入',
        watch: '观看',
        playMode: '🎮 游戏模式',
        watchMode: '👁️ 观战模式',
        villageWins: '🏘️ 村民胜利！',
        werewolvesWin: '🐺 狼人胜利！',
        villageWinMsg: '村民们成功消灭了所有狼人！',
        werewolvesWinMsg: '狼人已经占领了村庄！',
        playerJoined: '{name} 加入了游戏',
        gameStarted: '游戏开始！',
        foundDead: '{name} 被发现死亡',
        votedFor: '{voter} 投票给 {target}',
        phaseBegins: '{phase} 阶段开始',
        error: '错误',
        enterYourMessage: '输入你的消息...',
        youAre: '你的身份: {role}',
        sheriff: '警长'
    }
};

function t(key, params = {}) {
    let text = translations[currentLang][key] || translations['en'][key] || key;
    Object.keys(params).forEach(k => {
        text = text.replace(`{${k}}`, params[k]);
    });
    return text;
}

function updatePageLanguage() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });
    // Update select options
    document.querySelectorAll('option[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });
    // Update mode hint
    updateModeHint();
    // Update active language button
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-lang') === currentLang);
    });
}

function setLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('lang', lang);
    updatePageLanguage();
}

function updateModeHint() {
    const hint = document.getElementById('mode-hint');
    const humanSeatsGroup = document.getElementById('human-seats-group');
    if (hint) {
        hint.textContent = currentGameMode === 'play' ? t('playModeHint') : t('watchModeHint');
    }
    if (humanSeatsGroup) {
        humanSeatsGroup.style.display = currentGameMode === 'play' ? 'block' : 'none';
    }
}

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

function showView(viewId) {
    $$('.view').forEach(v => v.classList.remove('active'));
    $(`#${viewId}`).classList.add('active');
}

function showModal(content) {
    $('#modal-body').innerHTML = content;
    $('#modal').style.display = 'flex';
}

function hideModal() {
    $('#modal').style.display = 'none';
}

$('.modal-close')?.addEventListener('click', hideModal);
$('#modal')?.addEventListener('click', (e) => {
    if (e.target === $('#modal')) hideModal();
});

async function fetchAPI(endpoint, options = {}) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'API request failed');
    }
    return response.json();
}

async function loadGames() {
    try {
        const data = await fetchAPI('/api/games');
        renderGamesList(data.games);
    } catch (error) {
        console.error('Failed to load games:', error);
    }
}

function renderGamesList(games) {
    const list = $('#games-list');
    if (!games || games.length === 0) {
        list.innerHTML = `<p class="empty-state">${t('noActiveGames')}</p>`;
        return;
    }
    
    list.innerHTML = games.map(game => `
        <div class="game-item">
            <div>
                <strong>Game ${game.session_id}</strong>
                <span class="status status-${game.status}">${game.status}</span>
            </div>
            <div>
                <span>${game.players?.length || 0} ${t('players').toLowerCase()}</span>
                <button class="btn btn-primary" onclick="joinGame('${game.session_id}')">
                    ${game.status === 'waiting' ? t('join') : t('watch')}
                </button>
            </div>
        </div>
    `).join('');
}

async function createGame(e) {
    e.preventDefault();
    
    currentGameMode = $('#game-mode').value;
    const humanSeat = $('#human-seat')?.value;
    
    const formData = {
        role_set: $('#role-set').value,
        model_name: $('#model-name').value,
        backend: $('#backend').value,
        api_base: $('#api-base').value || null,
        api_key: $('#api-key').value || null,
        human_seats: currentGameMode === 'play' && humanSeat ? [parseInt(humanSeat)] : (currentGameMode === 'play' ? [] : null),
    };
    
    try {
        const data = await fetchAPI('/api/games', {
            method: 'POST',
            body: JSON.stringify(formData),
        });
        
        currentSession = data.session_id;
        $('#session-id').textContent = currentSession;
        
        // Show game mode in waiting room
        const modeDisplay = $('#game-mode-display');
        if (modeDisplay) {
            modeDisplay.textContent = currentGameMode === 'play' ? t('playMode') : t('watchMode');
            modeDisplay.className = `mode-badge ${currentGameMode}-mode`;
        }
        
        // Show/hide join form and start button based on mode
        const joinForm = $('#join-form');
        const startBtn = $('#start-game-btn');
        if (currentGameMode === 'play') {
            // Play mode: show join form, hide start button until joined
            if (joinForm) joinForm.style.display = 'flex';
            if (startBtn) startBtn.style.display = 'none';
        } else {
            // Watch mode: hide join form, show start button immediately
            if (joinForm) joinForm.style.display = 'none';
            if (startBtn) startBtn.style.display = 'block';
        }
        
        showView('waiting-room');
        connectWebSocket();
    } catch (error) {
        alert('Failed to create game: ' + error.message);
    }
}

async function joinGame(sessionId) {
    currentSession = sessionId;
    $('#session-id').textContent = currentSession;
    
    // Fetch game info to determine mode and show proper UI
    try {
        const gameInfo = await fetchAPI(`/api/games/${sessionId}`);
        const hasHumanPlayers = gameInfo.human_player_ids && gameInfo.human_player_ids.length > 0;
        currentGameMode = hasHumanPlayers ? 'play' : 'watch';
        
        // Show game mode
        const modeDisplay = $('#game-mode-display');
        if (modeDisplay) {
            modeDisplay.textContent = currentGameMode === 'play' ? t('playMode') : t('watchMode');
            modeDisplay.className = `mode-badge ${currentGameMode}-mode`;
        }
        
        // Show/hide join form and start button based on mode
        const joinForm = $('#join-form');
        const startBtn = $('#start-game-btn');
        if (currentGameMode === 'play') {
            if (joinForm) joinForm.style.display = 'flex';
            if (startBtn) startBtn.style.display = 'none';
        } else {
            if (joinForm) joinForm.style.display = 'none';
            if (startBtn) startBtn.style.display = 'block';
        }
    } catch (error) {
        console.error('Failed to fetch game info:', error);
    }
    
    showView('waiting-room');
    connectWebSocket();
    loadGameState();
}

async function joinAsPlayer() {
    const name = $('#player-name').value.trim();
    if (!name) {
        alert(currentLang === 'zh' ? '请输入你的名字' : 'Please enter your name');
        return;
    }
    
    try {
        const data = await fetchAPI(`/api/games/${currentSession}/join`, {
            method: 'POST',
            body: JSON.stringify({ player_name: name }),
        });
        
        currentPlayerId = data.player_id;
        $('#join-form').style.display = 'none';
        $('#start-game-btn').style.display = 'block';
        
        addEventLog({ type: 'info', message: t('playerJoined', { name: name }) });
    } catch (error) {
        alert('Failed to join: ' + error.message);
    }
}

async function startGame() {
    try {
        await fetchAPI(`/api/games/${currentSession}/start`, {
            method: 'POST',
        });
    } catch (error) {
        alert('Failed to start game: ' + error.message);
    }
}

function connectWebSocket() {
    if (ws) {
        ws.close();
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/games/${currentSession}${currentPlayerId ? `?player_id=${currentPlayerId}` : ''}`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleGameEvent(data);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
        setTimeout(() => {
            if (currentSession) {
                connectWebSocket();
            }
        }, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function handleGameEvent(event) {
    console.log('Game event:', event);
    
    switch (event.type) {
        case 'player_joined':
            addEventLog({ type: 'info', message: t('playerJoined', { name: event.player_name }) });
            loadGameState();
            break;
            
        case 'game_started':
            addEventLog({ type: 'info', message: t('gameStarted') });
            showView('game-view');
            loadGameState();
            break;
            
        case 'phase_change':
            updatePhaseDisplay(event);
            break;
            
        case 'death_announcement':
            addEventLog({ type: 'death', message: t('foundDead', { name: event.player_name || event.target_id }) });
            loadGameState();
            break;
            
        case 'speech':
            addEventLog({ type: 'speech', message: `${event.player_name || event.actor_id}: ${event.content}` });
            break;
            
        case 'vote_cast':
            addEventLog({ type: 'vote', message: t('votedFor', { voter: event.voter_name || event.actor_id, target: event.target_name || event.target_id }) });
            break;
            
        case 'action_required':
            showActionPanel(event);
            break;
            
        case 'game_finished':
            showGameResult(event);
            break;
            
        case 'game_error':
            addEventLog({ type: 'error', message: `${t('error')}: ${event.error}` });
            break;
            
        default:
            if (event.message) {
                addEventLog({ type: 'info', message: event.message });
            }
    }
}

async function loadGameState() {
    if (!currentSession) return;
    
    try {
        const state = await fetchAPI(`/api/games/${currentSession}/state${currentPlayerId ? `?player_id=${currentPlayerId}` : ''}`);
        renderGameState(state);
    } catch (error) {
        console.error('Failed to load game state:', error);
    }
}

function renderGameState(state) {
    if (state.waiting_for_players) {
        return;
    }
    
    $('#day-number').textContent = t('dayN', { n: state.day_number });
    const phaseEl = $('#phase');
    const phaseName = state.phase.toLowerCase();
    phaseEl.textContent = phaseName === 'night' ? t('night') : t('day');
    phaseEl.className = phaseName;
    
    const playersGrid = $('#game-players');
    playersGrid.innerHTML = state.players.map(player => `
        <div class="player-card ${player.is_alive ? '' : 'dead'}">
            <div class="player-avatar">${player.seat_number}</div>
            <div class="player-info">
                <div class="player-name">${player.name}</div>
                ${player.role ? `<div class="player-role">${player.role}</div>` : ''}
                <div class="player-status">
                    ${player.is_sheriff ? `👑 ${t('sheriff')}` : ''}
                    ${!player.is_alive ? '💀' : ''}
                </div>
            </div>
        </div>
    `).join('');
    
    if (currentPlayerId) {
        const myPlayer = state.players.find(p => p.id === currentPlayerId);
        if (myPlayer && myPlayer.role) {
            $('#player-role-info').textContent = t('youAre', { role: myPlayer.role });
        }
    }
}

function showActionPanel(event) {
    const panel = $('#action-panel');
    panel.style.display = 'block';
    
    $('#action-prompt').textContent = event.prompt || t('selectAction');
    
    const targetsDiv = $('#action-targets');
    const inputDiv = $('#action-input');
    
    targetsDiv.innerHTML = '';
    inputDiv.innerHTML = '';
    selectedTarget = null;
    
    if (event.targets && event.targets.length > 0) {
        targetsDiv.innerHTML = event.targets.map(target => `
            <button class="target-btn" data-target="${target.id}" onclick="selectTarget('${target.id}')">
                ${target.name || target.id}
            </button>
        `).join('');
    }
    
    if (event.action_type === 'speech' || event.action_type === 'last_words') {
        inputDiv.innerHTML = `
            <textarea id="speech-input" placeholder="${t('enterYourMessage')}"></textarea>
        `;
    }
}

function selectTarget(targetId) {
    $$('.target-btn').forEach(btn => btn.classList.remove('selected'));
    $(`.target-btn[data-target="${targetId}"]`)?.classList.add('selected');
    selectedTarget = targetId;
}

async function submitAction() {
    if (!currentSession || !currentPlayerId) return;
    
    const actionData = {
        player_id: currentPlayerId,
        action_type: 'action',
        data: {},
    };
    
    if (selectedTarget) {
        actionData.data.target = selectedTarget;
    }
    
    const speechInput = $('#speech-input');
    if (speechInput) {
        actionData.data.text = speechInput.value;
    }
    
    try {
        await fetchAPI(`/api/games/${currentSession}/action`, {
            method: 'POST',
            body: JSON.stringify(actionData),
        });
        
        $('#action-panel').style.display = 'none';
    } catch (error) {
        alert('Failed to submit action: ' + error.message);
    }
}

function showGameResult(event) {
    showView('result-view');
    
    const isVillageWin = event.winning_team === 'village';
    $('#result-title').textContent = isVillageWin ? t('villageWins') : t('werewolvesWin');
    
    $('#result-content').innerHTML = `
        <div class="winner ${event.winning_team}">
            ${isVillageWin ? t('villageWinMsg') : t('werewolvesWinMsg')}
        </div>
    `;
}

function addEventLog(event) {
    const log = $('#event-log');
    const time = new Date().toLocaleTimeString();
    
    const item = document.createElement('div');
    item.className = `event-item ${event.type || ''}`;
    item.innerHTML = `
        <span class="event-time">${time}</span>
        <span class="event-message">${event.message}</span>
    `;
    
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
}

function updatePhaseDisplay(event) {
    $('#day-number').textContent = t('dayN', { n: event.day_number });
    const phaseEl = $('#phase');
    const phaseName = event.phase.toLowerCase();
    phaseEl.textContent = phaseName === 'night' ? t('night') : t('day');
    phaseEl.className = phaseName;
    
    addEventLog({ type: 'info', message: t('phaseBegins', { phase: phaseName === 'night' ? t('night') : t('day') }) });
}

$('#create-game-form')?.addEventListener('submit', createGame);
$('#join-btn')?.addEventListener('click', joinAsPlayer);
$('#start-game-btn')?.addEventListener('click', startGame);
$('#refresh-games')?.addEventListener('click', loadGames);
$('#submit-action')?.addEventListener('click', submitAction);
$('#new-game-btn')?.addEventListener('click', () => {
    currentSession = null;
    currentPlayerId = null;
    currentGameMode = 'play';
    if (ws) ws.close();
    showView('lobby');
    loadGames();
});
$('#leave-btn')?.addEventListener('click', () => {
    currentSession = null;
    currentPlayerId = null;
    currentGameMode = 'play';
    if (ws) ws.close();
    showView('lobby');
    loadGames();
});

$('#backend')?.addEventListener('change', (e) => {
    const apiConfig = $$('.api-config');
    apiConfig.forEach(el => {
        el.style.display = e.target.value === 'api' ? 'block' : 'none';
    });
});

$('#game-mode')?.addEventListener('change', (e) => {
    currentGameMode = e.target.value;
    updateModeHint();
});

// Language switcher
document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        setLanguage(btn.getAttribute('data-lang'));
    });
});

document.addEventListener('DOMContentLoaded', () => {
    showView('lobby');
    loadGames();
    updatePageLanguage();
});
