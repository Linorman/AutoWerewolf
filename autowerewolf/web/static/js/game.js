const API_BASE = '/api';

const GameState = {
    gameId: null,
    ws: null,
    mode: 'watch',
    selectedTarget: null,
    autoScroll: true,
    userScrolled: false,
    lastDay: 0,
    lastPhase: '',
    activeFilters: new Set(['all'])
};

function initModeSelector() {
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            GameState.mode = btn.dataset.mode;
            
            const playConfig = document.getElementById('play-config');
            if (GameState.mode === 'play') {
                playConfig.classList.remove('hidden');
            } else {
                playConfig.classList.add('hidden');
            }
        });
    });
}

function initBackendSelector() {
    const backendSelect = document.getElementById('backend-select');
    backendSelect.addEventListener('change', (e) => {
        const isApi = e.target.value === 'api';
        document.getElementById('api-base-group').classList.toggle('hidden', !isApi);
        document.getElementById('api-key-group').classList.toggle('hidden', !isApi);
        document.getElementById('ollama-url-group').classList.toggle('hidden', isApi);
    });
}

function initCorrectorConfig() {
    const enableCorrectorCheckbox = document.getElementById('enable-corrector');
    const useSeparateModelCheckbox = document.getElementById('use-separate-model');
    const correctorOptions = document.getElementById('corrector-options');
    const correctorModelConfig = document.getElementById('corrector-model-config');
    const correctorBackendSelect = document.getElementById('corrector-backend');

    if (enableCorrectorCheckbox && correctorOptions) {
        const setCorrectorVisibility = (checked) => {
            correctorOptions.classList.toggle('hidden', !checked);
        };

        setCorrectorVisibility(enableCorrectorCheckbox.checked);

        enableCorrectorCheckbox.addEventListener('change', (e) => setCorrectorVisibility(e.target.checked));
    }

    if (useSeparateModelCheckbox && correctorModelConfig) {
        const setModelConfigVisibility = (checked) => {
            console.log('setModelConfigVisibility called, checked:', checked);
            console.log('Before toggle, hidden class present:', correctorModelConfig.classList.contains('hidden'));
            correctorModelConfig.classList.toggle('hidden', !checked);
            console.log('After toggle, hidden class present:', correctorModelConfig.classList.contains('hidden'));
        };

        setModelConfigVisibility(useSeparateModelCheckbox.checked);

        useSeparateModelCheckbox.addEventListener('change', (e) => {
            console.log('change event triggered, e.target.checked:', e.target.checked);
            setModelConfigVisibility(e.target.checked);
        });
    } else {
        console.warn('useSeparateModelCheckbox:', useSeparateModelCheckbox, 'correctorModelConfig:', correctorModelConfig);
    }

    if (correctorBackendSelect) {
        const updateCorrectorBackendVisibility = (val) => {
            const isApi = val === 'api';
            const apiBase = document.getElementById('corrector-api-base-group');
            const apiKey = document.getElementById('corrector-api-key-group');
            const ollamaUrl = document.getElementById('corrector-ollama-url-group');
            if (apiBase) apiBase.classList.toggle('hidden', !isApi);
            if (apiKey) apiKey.classList.toggle('hidden', !isApi);
            if (ollamaUrl) ollamaUrl.classList.toggle('hidden', isApi);
        };

        updateCorrectorBackendVisibility(correctorBackendSelect.value);

        correctorBackendSelect.addEventListener('change', (e) => updateCorrectorBackendVisibility(e.target.value));
    }
}

function initGameControls() {
    document.getElementById('start-btn').addEventListener('click', startGame);
    document.getElementById('stop-btn').addEventListener('click', stopGame);
    document.getElementById('auto-scroll-btn').addEventListener('click', toggleAutoScroll);
    document.getElementById('clear-log-btn').addEventListener('click', clearEventLog);
    initEventFilters();
    initTimelineScroll();
}

function toggleAutoScroll() {
    GameState.autoScroll = !GameState.autoScroll;
    GameState.userScrolled = false;
    document.getElementById('auto-scroll-btn').classList.toggle('active', GameState.autoScroll);
    if (GameState.autoScroll) {
        const timeline = document.getElementById('event-timeline');
        timeline.scrollTop = timeline.scrollHeight;
    }
}

function initTimelineScroll() {
    const timeline = document.getElementById('event-timeline');
    timeline.addEventListener('scroll', () => {
        if (!GameState.autoScroll) return;
        const isAtBottom = timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 20;
        GameState.userScrolled = !isAtBottom;
    });
}

function initEventFilters() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const filter = btn.dataset.filter;
            if (filter === 'all') {
                GameState.activeFilters.clear();
                GameState.activeFilters.add('all');
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            } else {
                GameState.activeFilters.delete('all');
                document.querySelector('.filter-btn[data-filter="all"]').classList.remove('active');
                btn.classList.toggle('active');
                if (btn.classList.contains('active')) {
                    GameState.activeFilters.add(filter);
                } else {
                    GameState.activeFilters.delete(filter);
                }
                if (GameState.activeFilters.size === 0) {
                    GameState.activeFilters.add('all');
                    document.querySelector('.filter-btn[data-filter="all"]').classList.add('active');
                }
            }
            applyEventFilters();
        });
    });
}

function applyEventFilters() {
    const timeline = document.getElementById('event-timeline');
    const items = timeline.querySelectorAll('.event-item');
    const showAll = GameState.activeFilters.has('all');
    items.forEach(item => {
        if (showAll) {
            item.style.display = '';
            return;
        }
        const category = item.dataset.category || 'system';
        item.style.display = GameState.activeFilters.has(category) ? '' : 'none';
    });
}

function clearEventLog() {
    const timeline = document.getElementById('event-timeline');
    timeline.innerHTML = `<div class="timeline-placeholder" id="timeline-placeholder">
        <p data-i18n="events_appear">${I18N.t('events_appear', 'Events will appear here')}</p>
    </div>`;
    GameState.lastDay = 0;
    GameState.lastPhase = '';
}

async function startGame() {
    const useSeparateModel = document.getElementById('use-separate-model').checked;
    
    const config = {
        mode: GameState.mode,
        model_config_data: {
            backend: document.getElementById('backend-select').value,
            model_name: document.getElementById('model-name').value,
            api_base: document.getElementById('api-base').value || null,
            api_key: document.getElementById('api-key').value || null,
            ollama_base_url: document.getElementById('ollama-url').value || null,
            temperature: parseFloat(document.getElementById('temperature').value),
            max_tokens: parseInt(document.getElementById('max-tokens').value),
            enable_corrector: document.getElementById('enable-corrector').checked,
            corrector_max_retries: parseInt(document.getElementById('corrector-retries').value),
        },
        output_corrector_config: {
            enabled: document.getElementById('enable-corrector').checked,
            max_retries: parseInt(document.getElementById('corrector-retries').value),
            use_separate_model: useSeparateModel,
            corrector_backend: useSeparateModel ? document.getElementById('corrector-backend').value : null,
            corrector_model_name: useSeparateModel ? (document.getElementById('corrector-model').value || null) : null,
            corrector_api_base: useSeparateModel ? (document.getElementById('corrector-api-base').value || null) : null,
            corrector_api_key: useSeparateModel ? (document.getElementById('corrector-api-key').value || null) : null,
            corrector_ollama_base_url: useSeparateModel ? (document.getElementById('corrector-ollama-url').value || null) : null,
        },
        game_config: {
            role_set: document.getElementById('role-set').value,
            random_seed: document.getElementById('random-seed').value 
                ? parseInt(document.getElementById('random-seed').value) 
                : null,
        },
    };

    if (GameState.mode === 'play') {
        config.player_seat = parseInt(document.getElementById('player-seat').value);
        config.player_name = document.getElementById('player-name').value;
    }

    const startBtn = document.getElementById('start-btn');
    startBtn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/games`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        
        const data = await res.json();
        GameState.gameId = data.game_id;
        
        connectWebSocket(GameState.gameId);
        
        startBtn.classList.add('hidden');
        document.getElementById('stop-btn').classList.remove('hidden');
        document.getElementById('arena-placeholder').classList.add('hidden');
        document.getElementById('player-grid').classList.remove('hidden');
        
        clearEventLog();
        
    } catch (e) {
        console.error('Start game error:', e);
        alert(`Failed to start game: ${e.message}`);
    } finally {
        startBtn.disabled = false;
    }
}

async function stopGame() {
    if (!GameState.gameId) return;
    
    try {
        await fetch(`${API_BASE}/games/${GameState.gameId}`, { method: 'DELETE' });
        
        if (GameState.ws) {
            GameState.ws.close();
            GameState.ws = null;
        }
        
        GameState.gameId = null;
        
        document.getElementById('start-btn').classList.remove('hidden');
        document.getElementById('stop-btn').classList.add('hidden');
        document.getElementById('game-status-text').textContent = I18N.t('stopped', 'Stopped');
        
    } catch (e) {
        console.error('Stop game error:', e);
    }
}

function connectWebSocket(gameId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    GameState.ws = new WebSocket(`${protocol}//${window.location.host}/ws/game/${gameId}`);
    
    GameState.ws.onopen = () => {
        updateConnectionStatus(true);
    };
    
    GameState.ws.onclose = () => {
        updateConnectionStatus(false);
    };
    
    GameState.ws.onerror = (e) => {
        console.error('WebSocket error:', e);
        updateConnectionStatus(false);
    };
    
    GameState.ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWSMessage(msg);
        } catch (e) {
            console.error('Parse message error:', e);
        }
    };
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-status');
    const statusText = indicator.querySelector('.status-text');
    
    if (connected) {
        indicator.classList.add('connected');
        statusText.textContent = I18N.t('connected', 'Connected');
    } else {
        indicator.classList.remove('connected');
        statusText.textContent = I18N.t('disconnected', 'Disconnected');
    }
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
            showActionModal(msg.data);
            break;
        case 'error':
            console.error('Game error:', msg.data.message);
            break;
    }
}

function updateGameState(state) {
    document.getElementById('day-number').textContent = state.day_number;
    
    const isNight = state.phase === 'night';
    const phaseIcon = document.getElementById('phase-icon');
    phaseIcon.querySelector('.sun-icon').classList.toggle('hidden', isNight);
    phaseIcon.querySelector('.moon-icon').classList.toggle('hidden', !isNight);
    
    const phaseText = document.querySelector('.phase-text');
    phaseText.textContent = isNight ? I18N.t('night', 'Night') : I18N.t('day', 'Day');
    
    document.getElementById('game-status-text').textContent = I18N.t(state.status, state.status);
    
    const alivePlayers = state.players.filter(p => p.is_alive);
    document.getElementById('alive-count').textContent = alivePlayers.length;
    
    renderPlayers(state.players, state.sheriff_id);
}

function renderPlayers(players, sheriffId) {
    const grid = document.getElementById('player-grid');
    grid.innerHTML = '';
    
    players.forEach(player => {
        const card = document.createElement('div');
        const classes = ['player-card'];
        
        if (!player.is_alive) classes.push('dead');
        if (player.id === sheriffId) classes.push('sheriff');
        if (player.role === 'werewolf') classes.push('werewolf');
        else if (['seer', 'witch', 'hunter', 'guard', 'village_idiot'].includes(player.role)) {
            classes.push('special');
        }
        
        card.className = classes.join(' ');
        
        const roleClass = player.role !== 'hidden' ? player.role : '';
        const roleDisplay = player.role !== 'hidden' 
            ? I18N.t(player.role, player.role) 
            : '???';
        
        const statusText = player.is_alive 
            ? I18N.t('alive', 'Alive') 
            : I18N.t('dead', 'Dead');
        
        const sheriffBadge = player.id === sheriffId 
            ? '<span class="sheriff-badge">👑</span>' 
            : '';
        
        card.innerHTML = `
            <div class="player-seat">#${player.seat_number}</div>
            <div class="player-name">${escapeHtml(player.name)}</div>
            <div class="player-role ${roleClass}">${roleDisplay}</div>
            <div class="player-status">${statusText}${sheriffBadge}</div>
        `;
        
        grid.appendChild(card);
    });
}

function addEvent(event) {
    const timeline = document.getElementById('event-timeline');
    const placeholder = document.getElementById('timeline-placeholder');
    if (placeholder) placeholder.remove();
    
    if (event.day_number !== GameState.lastDay || event.phase !== GameState.lastPhase) {
        if (GameState.lastDay !== 0 || GameState.lastPhase !== '') {
            const divider = document.createElement('div');
            divider.className = 'day-divider';
            const phaseEmoji = event.phase === 'night' ? '🌙' : '☀️';
            const phaseText = event.phase === 'night' 
                ? I18N.t('night', 'Night') 
                : I18N.t('day', 'Day');
            divider.textContent = `${phaseEmoji} ${I18N.t('day', 'Day')} ${event.day_number} - ${phaseText}`;
            timeline.appendChild(divider);
        }
        GameState.lastDay = event.day_number;
        GameState.lastPhase = event.phase;
    }
    
    const item = document.createElement('div');
    let eventClass = 'event-item';
    let badgeClass = 'system';
    let badgeText = event.event_type;
    let category = 'system';
    
    if (event.event_type === 'speech') {
        eventClass += ' speech';
        badgeClass = 'speech';
        badgeText = event.data?.is_last_words 
            ? I18N.t('last_words', 'Last Words') 
            : I18N.t('speech', 'Speech');
        category = 'speech';
    } else if (event.event_type.includes('death') || event.event_type === 'lynch' || event.event_type.includes('shot')) {
        eventClass += ' death';
        badgeClass = 'death';
        if (event.event_type === 'death_announcement') badgeText = '💀 ' + I18N.t('dead', 'Dead');
        else if (event.event_type === 'lynch') badgeText = '⚖️ Lynch';
        else if (event.event_type === 'hunter_shot') badgeText = '🔫 Shot';
        category = 'death';
    } else if (event.event_type.includes('vote')) {
        eventClass += ' vote';
        badgeClass = 'vote';
        badgeText = '🗳️ ' + I18N.t('vote', 'Vote');
        category = 'vote';
    } else if (event.event_type.includes('sheriff') || event.event_type.includes('badge')) {
        eventClass += ' sheriff';
        badgeClass = 'sheriff';
        badgeText = '👑 Sheriff';
        category = 'sheriff';
    }
    
    item.className = eventClass;
    item.dataset.category = category;
    
    const showAll = GameState.activeFilters.has('all');
    if (!showAll && !GameState.activeFilters.has(category)) {
        item.style.display = 'none';
    }
    
    const phaseEmoji = event.phase === 'night' ? '🌙' : '☀️';
    
    item.innerHTML = `
        <div class="event-header">
            <span class="event-badge ${badgeClass}">${badgeText}</span>
            <span class="event-phase">${phaseEmoji}</span>
        </div>
        <div class="event-content">${formatEventContent(event)}</div>
    `;
    
    timeline.appendChild(item);
    
    if (GameState.autoScroll && !GameState.userScrolled) {
        timeline.scrollTop = timeline.scrollHeight;
    }
}

function formatEventContent(event) {
    let content = escapeHtml(event.description || event.event_type);
    
    if (event.actor_name) {
        content = content.replace(
            new RegExp(escapeRegExp(event.actor_name), 'g'),
            `<span class="speaker">${escapeHtml(event.actor_name)}</span>`
        );
    }
    if (event.target_name && event.target_name !== event.actor_name) {
        content = content.replace(
            new RegExp(escapeRegExp(event.target_name), 'g'),
            `<span class="target">${escapeHtml(event.target_name)}</span>`
        );
    }
    
    return content;
}

function addNarration(content) {
    const timeline = document.getElementById('event-timeline');
    const placeholder = document.getElementById('timeline-placeholder');
    if (placeholder) placeholder.remove();
    
    const item = document.createElement('div');
    item.className = 'event-item narration';
    item.dataset.category = 'narration';
    item.innerHTML = `
        <div class="event-header">
            <span class="event-badge narration">📢 Moderator</span>
        </div>
        <div class="event-content">${escapeHtml(content)}</div>
    `;
    
    const showAll = GameState.activeFilters.has('all');
    if (!showAll && !GameState.activeFilters.has('narration')) {
        item.style.display = 'none';
    }
    
    timeline.appendChild(item);
    
    if (GameState.autoScroll && !GameState.userScrolled) {
        timeline.scrollTop = timeline.scrollHeight;
    }
}

function showWinner(team) {
    const modal = document.getElementById('winner-modal');
    const winnerModal = modal.querySelector('.winner-modal');
    const icon = document.getElementById('winner-icon');
    const title = document.getElementById('winner-title');
    const subtitle = document.getElementById('winner-subtitle');
    
    winnerModal.className = 'winner-modal ' + team;
    
    if (team === 'village') {
        icon.textContent = '🎉';
        title.textContent = I18N.t('village_wins', 'Village Wins!');
        subtitle.textContent = I18N.t('good_team_victory', 'The village has successfully eliminated all werewolves!');
    } else {
        icon.textContent = '🐺';
        title.textContent = I18N.t('werewolf_wins', 'Werewolves Win!');
        subtitle.textContent = I18N.t('evil_team_victory', 'The werewolves have taken over the village!');
    }
    
    modal.classList.remove('hidden');
}

function closeWinnerModal() {
    document.getElementById('winner-modal').classList.add('hidden');
}

function showActionModal(data) {
    const modal = document.getElementById('action-modal');
    document.getElementById('action-title').textContent = data.prompt || I18N.t('your_turn', 'Your Turn');
    
    const targets = document.getElementById('action-targets');
    targets.innerHTML = '';
    GameState.selectedTarget = null;
    
    if (data.valid_targets) {
        data.valid_targets.forEach(target => {
            const btn = document.createElement('div');
            btn.className = 'action-target';
            btn.textContent = target;
            btn.onclick = () => {
                document.querySelectorAll('.action-target').forEach(t => t.classList.remove('selected'));
                btn.classList.add('selected');
                GameState.selectedTarget = target;
            };
            targets.appendChild(btn);
        });
    }
    
    const speechInput = document.getElementById('speech-input');
    if (data.action_type === 'speech') {
        speechInput.classList.remove('hidden');
        speechInput.placeholder = I18N.t('enter_speech', 'Enter your speech...');
    } else {
        speechInput.classList.add('hidden');
    }
    
    modal.classList.remove('hidden');
}

function submitAction() {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    
    const action = {
        type: 'action',
        data: {
            action_type: 'submit',
            target_id: GameState.selectedTarget,
            content: document.getElementById('speech-input').value,
        }
    };
    
    GameState.ws.send(JSON.stringify(action));
    document.getElementById('action-modal').classList.add('hidden');
    document.getElementById('speech-input').value = '';
}

function skipAction() {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    
    GameState.ws.send(JSON.stringify({ type: 'action', data: { action_type: 'skip' } }));
    document.getElementById('action-modal').classList.add('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

document.addEventListener('DOMContentLoaded', () => {
    initModeSelector();
    initBackendSelector();
    initCorrectorConfig();
    initGameControls();
    document.getElementById('auto-scroll-btn').classList.add('active');
});

window.closeWinnerModal = closeWinnerModal;
window.submitAction = submitAction;
window.skipAction = skipAction;

