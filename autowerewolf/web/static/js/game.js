// API configuration - default to port 8000 for API server
const API_PORT = 8000;
const API_HOST = window.location.hostname;
const API_BASE = `http://${API_HOST}:${API_PORT}/api`;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${API_HOST}:${API_PORT}`;

const GameState = {
    gameId: null,
    ws: null,
    mode: 'watch',
    selectedTarget: null,
    autoScroll: true,
    userScrolled: false,
    lastDay: 0,
    lastPhase: '',
    activeFilters: new Set(['all']),
    humanPlayerView: null,
    currentActionRequest: null
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
            language: document.getElementById('game-language').value,
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
        
        if (GameState.mode === 'play') {
            document.getElementById('human-player-panel').classList.remove('hidden');
        } else {
            document.getElementById('human-player-panel').classList.add('hidden');
        }
        
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
        document.getElementById('human-player-panel').classList.add('hidden');
        GameState.humanPlayerView = null;
        
    } catch (e) {
        console.error('Stop game error:', e);
    }
}

function connectWebSocket(gameId) {
    GameState.ws = new WebSocket(`${WS_BASE}/ws/game/${gameId}`);
    
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
            if (msg.data) {
                addEvent(msg.data);
            }
            break;
        case 'narration':
            addNarration(msg.data.content);
            break;
        case 'game_over':
            showWinner(msg.data.winning_team);
            break;
        case 'action_request':
            GameState.currentActionRequest = msg.data;
            showActionModal(msg.data);
            break;
        case 'action_response':
            console.log('Action response:', msg.data);
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
    
    if (state.human_player_view) {
        GameState.humanPlayerView = state.human_player_view;
        updateHumanPlayerPanel(state.human_player_view);
    }
    
    renderPlayers(state.players, state.sheriff_id);
}

function updateHumanPlayerPanel(view) {
    const panel = document.getElementById('human-player-panel');
    const roleDisplay = document.getElementById('human-role-display');
    const infoContainer = document.getElementById('human-player-info');
    
    if (!view) {
        panel.classList.add('hidden');
        return;
    }
    
    panel.classList.remove('hidden');
    
    const roleText = I18N.t(view.role, view.role.replace('_', ' '));
    const roleIcon = getRoleIcon(view.role);
    roleDisplay.innerHTML = `${roleIcon} ${roleText}`;
    roleDisplay.className = `human-player-role ${view.role}`;
    
    let infoHtml = '';
    
    infoHtml += `<div class="human-info-item">
        <span class="label">${I18N.t('alignment', 'Alignment')}:</span>
        <span class="value ${view.alignment === 'village' ? 'good' : 'evil'}">${I18N.t(view.alignment, view.alignment)}</span>
    </div>`;
    
    infoHtml += `<div class="human-info-item">
        <span class="label">${I18N.t('status', 'Status')}:</span>
        <span class="value">${view.is_alive ? I18N.t('alive', 'Alive') : I18N.t('dead', 'Dead')}</span>
    </div>`;
    
    if (view.is_sheriff) {
        infoHtml += `<div class="human-info-item">
            <span class="value">👑 ${I18N.t('sheriff', 'Sheriff')}</span>
        </div>`;
    }
    
    const privateInfo = view.private_info || {};
    
    if (privateInfo.teammates && privateInfo.teammates.length > 0) {
        infoHtml += `<div class="human-info-item">
            <span class="label">🐺 ${I18N.t('teammates', 'Teammates')}:</span>
            <div class="teammate-list">`;
        privateInfo.teammates.forEach(t => {
            const deadClass = t.is_alive ? '' : 'dead';
            infoHtml += `<span class="teammate-tag ${deadClass}">${escapeHtml(t.name)}</span>`;
        });
        infoHtml += `</div></div>`;
    }
    
    if (privateInfo.check_results && privateInfo.check_results.length > 0) {
        infoHtml += `<div class="human-info-item">
            <span class="label">🔮 ${I18N.t('seer_checks', 'Seer Checks')}:</span>
            <div class="teammate-list">`;
        privateInfo.check_results.forEach(r => {
            const resultClass = r.result === 'village' ? 'good' : 'evil';
            const playerName = r.player_name || r.player_id;
            infoHtml += `<span class="teammate-tag" style="background: rgba(${resultClass === 'good' ? '34,197,94' : '201,72,91'}, 0.2); color: var(--accent-${resultClass === 'good' ? 'success' : 'primary'});">${escapeHtml(playerName)}: ${I18N.t(r.result, r.result)}</span>`;
        });
        infoHtml += `</div></div>`;
    }
    
    if (view.role === 'witch') {
        infoHtml += `<div class="human-info-item">
            <span class="label">💊 ${I18N.t('cure', 'Cure')}:</span>
            <span class="value">${privateInfo.has_cure ? '✓' : '✗'}</span>
        </div>`;
        infoHtml += `<div class="human-info-item">
            <span class="label">☠️ ${I18N.t('poison', 'Poison')}:</span>
            <span class="value">${privateInfo.has_poison ? '✓' : '✗'}</span>
        </div>`;
        if (privateInfo.attack_target) {
            infoHtml += `<div class="human-info-item">
                <span class="label">⚠️ ${I18N.t('attack_target', 'Attack Target')}:</span>
                <span class="value evil">${escapeHtml(privateInfo.attack_target.name)}</span>
            </div>`;
        }
    }
    
    if (view.role === 'hunter') {
        infoHtml += `<div class="human-info-item">
            <span class="label">🔫 ${I18N.t('can_shoot', 'Can Shoot')}:</span>
            <span class="value">${privateInfo.can_shoot ? '✓' : '✗'}</span>
        </div>`;
    }
    
    if (view.role === 'guard' && privateInfo.last_protected) {
        const lastProtectedName = typeof privateInfo.last_protected === 'object' 
            ? privateInfo.last_protected.name 
            : privateInfo.last_protected;
        infoHtml += `<div class="human-info-item">
            <span class="label">🛡️ ${I18N.t('last_protected', 'Last Protected')}:</span>
            <span class="value">${escapeHtml(lastProtectedName)}</span>
        </div>`;
    }
    
    infoContainer.innerHTML = infoHtml;
}

function getRoleIcon(role) {
    const icons = {
        'werewolf': '🐺',
        'seer': '🔮',
        'witch': '🧙',
        'hunter': '🔫',
        'guard': '🛡️',
        'village_idiot': '🃏',
        'villager': '👤'
    };
    return icons[role] || '👤';
}

function renderPlayers(players, sheriffId) {
    const grid = document.getElementById('player-grid');
    grid.innerHTML = '';
    
    players.forEach(player => {
        const card = document.createElement('div');
        const classes = ['player-card'];
        
        if (!player.is_alive) classes.push('dead');
        if (player.id === sheriffId) classes.push('sheriff');
        if (player.is_human) classes.push('human');
        if (player.is_teammate) classes.push('teammate');
        if (player.role === 'werewolf') classes.push('werewolf');
        else if (['seer', 'witch', 'hunter', 'guard', 'village_idiot'].includes(player.role)) {
            classes.push('special');
        }
        
        card.className = classes.join(' ');
        card.dataset.playerId = player.id;
        
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
        
        const teammateBadge = player.is_teammate
            ? '<span class="teammate-badge">🐺</span>'
            : '';
        
        const playerLabel = `Player ${player.seat_number}`;
        
        card.innerHTML = `
            <div class="player-seat">#${player.seat_number}</div>
            <div class="player-name">${escapeHtml(player.name)}${teammateBadge}</div>
            <div class="player-label">${playerLabel}</div>
            <div class="player-role ${roleClass}">${roleDisplay}</div>
            <div class="player-status">${statusText}${sheriffBadge}</div>
        `;
        
        grid.appendChild(card);
    });
}

function addEvent(event) {
    if (!event || !event.event_type) {
        return;
    }
    
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
    const actionType = data.action_type;
    const prompt = data.prompt || I18N.t('your_turn', 'Your Turn');
    
    document.getElementById('action-title').textContent = getActionTitle(actionType);
    document.getElementById('action-prompt').textContent = prompt;
    
    const playerInfo = document.getElementById('action-player-info');
    if (data.player_info && data.player_info.role) {
        playerInfo.textContent = `${getRoleIcon(data.player_info.role)} ${I18N.t(data.player_info.role, data.player_info.role)}`;
        playerInfo.classList.remove('hidden');
    } else {
        playerInfo.classList.add('hidden');
    }
    
    const targets = document.getElementById('action-targets');
    const yesNoButtons = document.getElementById('yes-no-buttons');
    const speechInput = document.getElementById('speech-input');
    const submitButtons = document.getElementById('action-submit-buttons');
    const skipBtn = document.getElementById('skip-btn');
    
    targets.innerHTML = '';
    GameState.selectedTarget = null;
    yesNoButtons.classList.add('hidden');
    speechInput.classList.add('hidden');
    submitButtons.classList.remove('hidden');
    
    let discussionContainer = document.getElementById('werewolf-discussion');
    if (discussionContainer) {
        discussionContainer.remove();
    }
    
    if (data.allow_skip) {
        skipBtn.classList.remove('hidden');
    } else {
        skipBtn.classList.add('hidden');
    }
    
    if (actionType === 'yes_no') {
        yesNoButtons.classList.remove('hidden');
        submitButtons.classList.add('hidden');
    } else if (actionType === 'text_input') {
        speechInput.classList.remove('hidden');
        speechInput.value = '';
        speechInput.placeholder = I18N.t('enter_text', 'Enter your response...');
        if (data.extra_context && data.extra_context.multiline) {
            speechInput.rows = 4;
        } else {
            speechInput.rows = 2;
        }
    } else if (actionType === 'target_selection') {
        const extraContext = data.extra_context || {};
        const aiProposals = extraContext.ai_proposals || [];
        
        if (extraContext.is_werewolf_discussion && aiProposals.length > 0) {
            discussionContainer = document.createElement('div');
            discussionContainer.id = 'werewolf-discussion';
            discussionContainer.className = 'werewolf-discussion';
            
            let discussionHtml = `<div class="discussion-header">🐺 ${I18N.t('teammates_suggestions', 'Teammates\' Suggestions')}</div>`;
            discussionHtml += '<div class="discussion-list">';
            
            aiProposals.forEach(proposal => {
                const targetName = proposal.proposed_target_name || proposal.proposed_target;
                discussionHtml += `
                    <div class="discussion-item">
                        <div class="discussion-wolf">${escapeHtml(proposal.werewolf_name)}</div>
                        <div class="discussion-target">${I18N.t('suggests_kill', 'suggests killing')} <strong>${escapeHtml(targetName)}</strong></div>
                        <div class="discussion-reason">${escapeHtml(proposal.reasoning)}</div>
                    </div>
                `;
            });
            
            discussionHtml += '</div>';
            discussionContainer.innerHTML = discussionHtml;
            
            const actionPrompt = document.getElementById('action-prompt');
            actionPrompt.parentNode.insertBefore(discussionContainer, actionPrompt.nextSibling);
        }
        
        const targetInfoList = data.valid_targets_info || [];
        const targetIds = data.valid_targets || [];
        
        if (targetInfoList.length > 0) {
            targetInfoList.forEach(targetInfo => {
                const btn = document.createElement('div');
                btn.className = 'action-target';
                const playerLabel = `Player ${targetInfo.seat_number}`;
                btn.innerHTML = `<span class="target-seat">#${targetInfo.seat_number}</span><span class="target-name">${escapeHtml(targetInfo.name)}</span><span class="target-label">(${playerLabel})</span>`;
                btn.dataset.targetId = targetInfo.id;
                btn.onclick = () => {
                    document.querySelectorAll('.action-target').forEach(t => t.classList.remove('selected'));
                    btn.classList.add('selected');
                    GameState.selectedTarget = targetInfo.id;
                };
                targets.appendChild(btn);
            });
        } else if (targetIds.length > 0) {
            targetIds.forEach(target => {
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
    }
    
    modal.classList.remove('hidden');
}

function getActionTitle(actionType) {
    const titles = {
        'target_selection': I18N.t('select_target', 'Select Target'),
        'yes_no': I18N.t('make_decision', 'Make Decision'),
        'text_input': I18N.t('enter_response', 'Enter Response'),
    };
    return titles[actionType] || I18N.t('your_turn', 'Your Turn');
}

function submitAction() {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    
    const currentRequest = GameState.currentActionRequest;
    const actionType = currentRequest ? currentRequest.action_type : 'submit';
    
    const action = {
        type: 'action',
        data: {
            action_type: actionType,
            target_id: GameState.selectedTarget,
            content: document.getElementById('speech-input').value,
            extra_data: {
                target: GameState.selectedTarget,
                text: document.getElementById('speech-input').value,
            }
        }
    };
    
    GameState.ws.send(JSON.stringify(action));
    document.getElementById('action-modal').classList.add('hidden');
    document.getElementById('speech-input').value = '';
    GameState.currentActionRequest = null;
}

function submitYesNo(value) {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    
    const action = {
        type: 'action',
        data: {
            action_type: 'yes_no',
            extra_data: {
                value: value
            }
        }
    };
    
    GameState.ws.send(JSON.stringify(action));
    document.getElementById('action-modal').classList.add('hidden');
    GameState.currentActionRequest = null;
}

function skipAction() {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    
    const action = {
        type: 'action',
        data: {
            action_type: 'skip',
            target_id: null,
            extra_data: {
                target: 'skip'
            }
        }
    };
    
    GameState.ws.send(JSON.stringify(action));
    document.getElementById('action-modal').classList.add('hidden');
    GameState.currentActionRequest = null;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function loadDefaults() {
    try {
        const response = await fetch(`${API_BASE}/defaults`);
        if (!response.ok) {
            console.warn('Failed to load defaults, using built-in defaults');
            return;
        }
        const defaults = await response.json();
        
        const mc = defaults.model_config;
        if (mc) {
            const backendSelect = document.getElementById('backend-select');
            if (backendSelect && mc.backend) {
                backendSelect.value = mc.backend;
                backendSelect.dispatchEvent(new Event('change'));
            }
            
            const modelName = document.getElementById('model-name');
            if (modelName && mc.model_name) modelName.value = mc.model_name;
            
            const apiBase = document.getElementById('api-base');
            if (apiBase && mc.api_base) apiBase.value = mc.api_base;
            
            const apiKey = document.getElementById('api-key');
            if (apiKey && mc.api_key) apiKey.value = mc.api_key;
            
            const ollamaUrl = document.getElementById('ollama-url');
            if (ollamaUrl && mc.ollama_base_url) ollamaUrl.value = mc.ollama_base_url;
            
            const temperature = document.getElementById('temperature');
            if (temperature && mc.temperature !== undefined) temperature.value = mc.temperature;
            
            const maxTokens = document.getElementById('max-tokens');
            if (maxTokens && mc.max_tokens !== undefined) maxTokens.value = mc.max_tokens;
            
            const enableCorrectorCheckbox = document.getElementById('enable-corrector');
            if (enableCorrectorCheckbox && mc.enable_corrector !== undefined) {
                enableCorrectorCheckbox.checked = mc.enable_corrector;
                enableCorrectorCheckbox.dispatchEvent(new Event('change'));
            }
            
            const correctorRetries = document.getElementById('corrector-retries');
            if (correctorRetries && mc.corrector_max_retries !== undefined) {
                correctorRetries.value = mc.corrector_max_retries;
            }
        }
        
        const oc = defaults.output_corrector_config;
        if (oc) {
            const useSeparateModel = document.getElementById('use-separate-model');
            if (useSeparateModel && oc.use_separate_model !== undefined) {
                useSeparateModel.checked = oc.use_separate_model;
                useSeparateModel.dispatchEvent(new Event('change'));
            }
            
            const correctorBackend = document.getElementById('corrector-backend');
            if (correctorBackend && oc.corrector_backend) {
                correctorBackend.value = oc.corrector_backend;
                correctorBackend.dispatchEvent(new Event('change'));
            }
            
            const correctorModelName = document.getElementById('corrector-model');
            if (correctorModelName && oc.corrector_model_name) {
                correctorModelName.value = oc.corrector_model_name;
            }
            
            const correctorApiBase = document.getElementById('corrector-api-base');
            if (correctorApiBase && oc.corrector_api_base) {
                correctorApiBase.value = oc.corrector_api_base;
            }
            
            const correctorApiKey = document.getElementById('corrector-api-key');
            if (correctorApiKey && oc.corrector_api_key) {
                correctorApiKey.value = oc.corrector_api_key;
            }
            
            const correctorOllamaUrl = document.getElementById('corrector-ollama-url');
            if (correctorOllamaUrl && oc.corrector_ollama_base_url) {
                correctorOllamaUrl.value = oc.corrector_ollama_base_url;
            }
        }
        
        const gc = defaults.game_config;
        if (gc) {
            const roleSet = document.getElementById('role-set');
            if (roleSet && gc.role_set) roleSet.value = gc.role_set;
            
            const gameLanguage = document.getElementById('game-language');
            if (gameLanguage && gc.language) gameLanguage.value = gc.language;
            
            const randomSeed = document.getElementById('random-seed');
            if (randomSeed && gc.random_seed !== null && gc.random_seed !== undefined) {
                randomSeed.value = gc.random_seed;
            }
        }
        
        console.log(`Config loaded from: ${defaults.config_source}`);
        console.log(`Game config loaded from: ${defaults.game_config_source}`);
        
    } catch (error) {
        console.warn('Error loading defaults:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initModeSelector();
    initBackendSelector();
    initCorrectorConfig();
    initGameControls();
    document.getElementById('auto-scroll-btn').classList.add('active');
    
    // Load defaults from server (config files or built-in defaults)
    loadDefaults();
});

window.closeWinnerModal = closeWinnerModal;
window.submitAction = submitAction;
window.submitYesNo = submitYesNo;
window.skipAction = skipAction;

