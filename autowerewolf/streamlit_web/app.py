import logging
import os
import time
import streamlit as st
from typing import Optional, List, Set

from autowerewolf.streamlit_web.i18n import t, set_language, get_language
from autowerewolf.streamlit_web.session import (
    StreamlitGameSession,
    StreamlitModelConfig,
    StreamlitGameConfig,
    StreamlitCorrectorConfig,
    session_manager,
    PlayerData,
    EventData,
)
from autowerewolf.streamlit_web.config_loader import streamlit_config_loader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="AutoWerewolf",
    page_icon="🐺",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROLE_ICONS = {
    "werewolf": "🐺",
    "seer": "🔮",
    "witch": "🧙",
    "hunter": "🔫",
    "guard": "🛡️",
    "village_idiot": "🃏",
    "villager": "👤",
    "hidden": "❓",
}


def init_session_state():
    if "app_initialized" not in st.session_state:
        logger.info("[App] ========== AutoWerewolf Streamlit App Starting ==========")
        st.session_state.app_initialized = True
    if "game_session" not in st.session_state:
        st.session_state.game_session = None
    if "ui_language" not in st.session_state:
        st.session_state.ui_language = "en"
    if "last_event_count" not in st.session_state:
        st.session_state.last_event_count = 0
    if "pending_action" not in st.session_state:
        st.session_state.pending_action = None
    if "action_submitted" not in st.session_state:
        st.session_state.action_submitted = False
    if "event_filters" not in st.session_state:
        st.session_state.event_filters = {"all"}
    if "show_winner_modal" not in st.session_state:
        st.session_state.show_winner_modal = False
    if "winner_team" not in st.session_state:
        st.session_state.winner_team = None
    if "config_loaded" not in st.session_state:
        logger.info("[App] Initializing session state and loading configurations...")
        streamlit_config_loader.load_from_file()
        streamlit_config_loader.load_game_config()
        st.session_state.config_loaded = True
        logger.info("[App] Session state initialized")


def get_session() -> Optional[StreamlitGameSession]:
    return st.session_state.get("game_session")


def render_sidebar():
    with st.sidebar:
        st.title("🐺 " + t("app_title"))
        
        lang = st.selectbox(
            t("language"),
            options=["en", "zh"],
            format_func=lambda x: "English" if x == "en" else "中文",
            index=0 if st.session_state.ui_language == "en" else 1,
            key="lang_select",
        )
        if lang != st.session_state.ui_language:
            st.session_state.ui_language = lang
            set_language(lang)
            st.rerun()
        
        set_language(st.session_state.ui_language)
        
        st.divider()
        
        session = get_session()
        game_running = session is not None and session.status == "running"
        
        status_color = "🟢" if game_running else "🔴"
        status_text = t("connected") if game_running else t("disconnected")
        st.caption(f"{status_color} {status_text}")
        
        mode = st.radio(
            t("mode"),
            options=["watch", "play"],
            format_func=lambda x: t("watch_mode") if x == "watch" else t("play_mode"),
            horizontal=True,
            disabled=game_running,
            key="mode_radio",
        )
        
        st.subheader(t("model_config"))
        
        default_mc = streamlit_config_loader.model_config
        default_cc = streamlit_config_loader.corrector_config
        default_gc = streamlit_config_loader.game_config
        
        backend = st.selectbox(
            t("backend"),
            options=["ollama", "api"],
            format_func=lambda x: "Ollama" if x == "ollama" else "API",
            index=0 if default_mc.backend == "ollama" else 1,
            disabled=game_running,
            key="backend_select",
        )
        
        model_name = st.text_input(
            t("model_name"),
            value=default_mc.model_name,
            disabled=game_running,
            key="model_name_input",
        )
        
        if backend == "ollama":
            ollama_url = st.text_input(
                t("ollama_url"),
                value=default_mc.ollama_base_url or "",
                placeholder="http://localhost:11434",
                disabled=game_running,
                key="ollama_url_input",
            )
            api_base = None
            api_key = None
        else:
            api_base = st.text_input(
                t("api_base"),
                value=default_mc.api_base or "",
                placeholder="https://api.openai.com/v1",
                disabled=game_running,
                key="api_base_input",
            )
            api_key = st.text_input(
                t("api_key"),
                value=default_mc.api_key or "",
                type="password",
                disabled=game_running,
                key="api_key_input",
            )
            ollama_url = None
        
        col1, col2 = st.columns(2)
        with col1:
            temperature = st.number_input(
                t("temperature"),
                min_value=0.0,
                max_value=2.0,
                value=default_mc.temperature,
                step=0.1,
                disabled=game_running,
                key="temp_input",
            )
        with col2:
            max_tokens = st.number_input(
                t("max_tokens"),
                min_value=100,
                value=default_mc.max_tokens,
                step=100,
                disabled=game_running,
                key="tokens_input",
            )
        
        with st.expander(t("output_corrector")):
            enable_corrector = st.checkbox(
                t("enable_corrector"),
                value=default_mc.enable_corrector,
                disabled=game_running,
                key="corrector_check",
            )
            
            if enable_corrector:
                corrector_retries = st.number_input(
                    t("corrector_retries"),
                    min_value=1,
                    max_value=5,
                    value=default_mc.corrector_max_retries,
                    disabled=game_running,
                    key="corrector_retries_input",
                )
                
                use_separate = st.checkbox(
                    t("use_separate_model"),
                    value=default_cc.use_separate_model,
                    disabled=game_running,
                    key="separate_model_check",
                )
                
                if use_separate:
                    corr_backend = st.selectbox(
                        t("corrector_backend"),
                        options=["ollama", "api"],
                        index=0 if default_cc.corrector_backend != "api" else 1,
                        disabled=game_running,
                        key="corr_backend_select",
                    )
                    corr_model = st.text_input(
                        t("corrector_model"),
                        value=default_cc.corrector_model_name or "",
                        disabled=game_running,
                        key="corr_model_input",
                    )
                    
                    if corr_backend == "ollama":
                        corr_ollama_url = st.text_input(
                            t("ollama_url"),
                            value=default_cc.corrector_ollama_base_url or "",
                            placeholder="http://localhost:11434",
                            disabled=game_running,
                            key="corr_ollama_url_input",
                        )
                        corr_api_base = None
                        corr_api_key = None
                    else:
                        corr_api_base = st.text_input(
                            t("api_base"),
                            value=default_cc.corrector_api_base or "",
                            placeholder="https://api.openai.com/v1",
                            disabled=game_running,
                            key="corr_api_base_input",
                        )
                        corr_api_key = st.text_input(
                            t("api_key"),
                            value=default_cc.corrector_api_key or "",
                            type="password",
                            disabled=game_running,
                            key="corr_api_key_input",
                        )
                        corr_ollama_url = None
                else:
                    corr_backend = None
                    corr_model = None
                    corr_ollama_url = None
                    corr_api_base = None
                    corr_api_key = None
            else:
                corrector_retries = 2
                use_separate = False
                corr_backend = None
                corr_model = None
                corr_ollama_url = None
                corr_api_base = None
                corr_api_key = None
        
        st.subheader(t("game_rules"))
        
        role_set = st.selectbox(
            t("role_set"),
            options=["A", "B"],
            format_func=lambda x: t("role_set_a") if x == "A" else t("role_set_b"),
            index=0 if default_gc.role_set == "A" else 1,
            disabled=game_running,
            key="role_set_select",
        )
        
        game_language = st.selectbox(
            t("game_language"),
            options=["en", "zh"],
            format_func=lambda x: "English" if x == "en" else "中文",
            index=0 if default_gc.language == "en" else 1,
            disabled=game_running,
            key="game_lang_select",
            help=t("game_language_hint"),
        )
        
        random_seed = st.text_input(
            t("random_seed"),
            value=str(default_gc.random_seed) if default_gc.random_seed else "",
            disabled=game_running,
            key="seed_input",
        )
        seed_value = int(random_seed) if random_seed.isdigit() else None
        
        if mode == "play":
            st.subheader(t("player_settings"))
            col1, col2 = st.columns(2)
            with col1:
                player_seat = st.selectbox(
                    t("your_seat"),
                    options=list(range(1, 13)),
                    disabled=game_running,
                    key="seat_select",
                )
            with col2:
                player_name = st.text_input(
                    t("your_name"),
                    value="Human Player",
                    disabled=game_running,
                    key="name_input",
                )
        else:
            player_seat = None
            player_name = None
        
        st.divider()
        
        if not game_running:
            if st.button(t("start_game"), type="primary", use_container_width=True, key="start_btn"):
                logger.info("[App] Start game button clicked")
                model_config = StreamlitModelConfig(
                    backend=backend,
                    model_name=model_name,
                    api_base=api_base or None,
                    api_key=api_key or None,
                    ollama_base_url=ollama_url or None,
                    temperature=temperature,
                    max_tokens=int(max_tokens),
                    enable_corrector=enable_corrector,
                    corrector_max_retries=int(corrector_retries),
                )
                
                game_config = StreamlitGameConfig(
                    role_set=role_set,
                    random_seed=seed_value,
                    language=game_language,
                )
                
                corrector_config = StreamlitCorrectorConfig(
                    enabled=enable_corrector,
                    max_retries=int(corrector_retries),
                    use_separate_model=use_separate,
                    corrector_backend=corr_backend,
                    corrector_model_name=corr_model,
                    corrector_api_base=corr_api_base or None,
                    corrector_api_key=corr_api_key or None,
                    corrector_ollama_base_url=corr_ollama_url or None,
                )
                
                logger.info(f"[App] Creating game session: mode={mode}, backend={backend}, model={model_name}")
                session = session_manager.create_session(
                    mode=mode,
                    model_config=model_config,
                    game_config=game_config,
                    corrector_config=corrector_config,
                    player_seat=player_seat,
                    player_name=player_name,
                )
                session.start()
                st.session_state.game_session = session
                st.session_state.last_event_count = 0
                logger.info(f"[App] Game session started: {session.game_id}")
                st.rerun()
                return
        else:
            if st.button(t("stop_game"), type="secondary", use_container_width=True, key="stop_btn"):
                if session:
                    logger.info(f"[App] Stop game button clicked for session: {session.game_id}")
                    session.stop()
                    st.session_state.game_session = None
                    logger.info("[App] Game session stopped and cleared")
                    st.rerun()
                    return


def render_player_card(player: PlayerData, sheriff_id: Optional[str] = None):
    role_icon = ROLE_ICONS.get(player.role, "❓")
    
    # Build HTML parts
    border_color = '#22c55e' if player.is_alive else '#6b7280'
    bg_color = '#1a1a2e' if player.is_alive else '#2d2d3d'
    opacity = '1' if player.is_alive else '0.6'
    sheriff_badge = '👑' if player.id == sheriff_id else ''
    role_text = t(player.role) if player.role != 'hidden' else t('hidden')
    teammate_icon = ' 🐺' if player.is_teammate else ''
    human_icon = ' ⭐' if player.is_human else ''
    status_color = '#22c55e' if player.is_alive else '#ef4444'
    status_text = t('alive') if player.is_alive else t('dead')
    
    card_html = f'''<div style="padding: 10px; border-radius: 8px; border: 2px solid {border_color}; background: {bg_color}; opacity: {opacity}; margin: 5px 0;">
<div style="display: flex; justify-content: space-between; align-items: center;">
<span style="font-weight: bold;">#{player.seat_number} {player.name}</span>
<span>{sheriff_badge}</span>
</div>
<div style="margin-top: 5px;">
<span>{role_icon} {role_text}</span>{teammate_icon}{human_icon}
</div>
<div style="font-size: 0.8em; color: {status_color};">
{status_text}
</div>
</div>'''
    
    st.markdown(card_html, unsafe_allow_html=True)


def render_game_arena(session: StreamlitGameSession):
    state = session.get_state()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t("day_number"), state["day_number"])
    with col2:
        phase = state["phase"]
        phase_icon = "🌙" if phase == "night" else "☀️"
        st.metric(t("current_phase"), f"{phase_icon} {t(phase)}")
    with col3:
        alive_count = sum(1 for p in state["players"] if p.is_alive)
        st.metric(t("players_alive"), f"{alive_count}/12")
    
    status = session.status
    if status == "running":
        st.info(f"🎮 {t('game_running')}")
    elif status == "completed":
        winning = state.get("winning_team")
        if winning == "village":
            st.success(t("village_wins"))
        else:
            st.error(t("werewolf_wins"))
        
        if not st.session_state.get("show_winner_modal"):
            st.session_state.show_winner_modal = True
            st.session_state.winner_team = winning
            logger.info(f"[App] Game completed. Winner: {winning}")
    elif status == "error":
        st.error(f"❌ {t('game_error')}: {session.error_message}")
        logger.error(f"[App] Game error displayed: {session.error_message}")
    elif status == "stopped":
        st.warning(f"⏹️ {t('game_stopped')}")
    
    st.subheader(t("players"))
    
    players = state.get("players", [])
    if players:
        cols = st.columns(4)
        for i, player in enumerate(players):
            with cols[i % 4]:
                render_player_card(player, state.get("sheriff_id"))


def render_human_panel(session: StreamlitGameSession):
    state = session.get_state()
    human_view = state.get("human_player_view")
    
    if not human_view:
        return
    
    st.subheader(f"🎯 {t('your_status')}")
    
    role = human_view.get("role", "hidden")
    role_icon = ROLE_ICONS.get(role, "❓")
    alignment = human_view.get("alignment", "hidden")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t("role"), f"{role_icon} {t(role)}")
    with col2:
        st.metric(t("alignment"), t(alignment))
    with col3:
        status_text = t("alive") if human_view.get("is_alive") else t("dead")
        if human_view.get("is_sheriff"):
            status_text = f"👑 {status_text}"
        st.metric(t("status"), status_text)
    
    private_info = human_view.get("private_info", {})
    
    if private_info:
        with st.expander(t("player_info"), expanded=True):
            if "teammates" in private_info:
                st.write(f"🐺 **{t('teammates')}:**")
                for tm in private_info["teammates"]:
                    status_icon = "✅" if tm["is_alive"] else "💀"
                    st.write(f"  {status_icon} {tm['name']}")
            
            if "check_results" in private_info:
                st.write(f"🔮 **{t('seer_checks')}:**")
                for check in private_info["check_results"]:
                    result_icon = "👤" if check["result"] == "village" else "🐺"
                    st.write(f"  {result_icon} {check['player_name']}: {t(check['result'])}")
            
            if "has_cure" in private_info:
                st.write(f"💊 **{t('cure')}:** {'✅' if private_info['has_cure'] else '❌'}")
                st.write(f"☠️ **{t('poison')}:** {'✅' if private_info.get('has_poison') else '❌'}")
                if "attack_target" in private_info:
                    st.write(f"⚠️ **{t('attack_target')}:** {private_info['attack_target']['name']}")
            
            if "can_shoot" in private_info:
                st.write(f"🔫 **{t('can_shoot')}:** {'✅' if private_info['can_shoot'] else '❌'}")
            
            if "last_protected" in private_info and private_info["last_protected"]:
                st.write(f"🛡️ **{t('last_protected')}:** {private_info['last_protected']['name']}")
            
            if "revealed" in private_info:
                st.write(f"🃏 **{t('revealed')}:** {'✅' if private_info['revealed'] else '❌'}")


def render_action_panel(session: StreamlitGameSession):
    action = session.get_action_request(timeout=0.05)
    
    if action:
        st.session_state.pending_action = action
        st.session_state.action_submitted = False
        logger.info(f"[App] New action request received: {action.get('action_type')}")
    
    pending = st.session_state.get("pending_action")
    if not pending or st.session_state.get("action_submitted"):
        return
    
    st.subheader(f"⚡ {t('your_turn')}")
    
    action_type = pending.get("action_type")
    prompt = pending.get("prompt", "")
    valid_targets = pending.get("valid_targets_info", [])
    allow_skip = pending.get("allow_skip", False)
    extra_context = pending.get("extra_context", {})
    
    st.info(prompt)
    
    if extra_context.get("is_werewolf_discussion"):
        ai_proposals = extra_context.get("ai_proposals", [])
        if ai_proposals:
            with st.expander(f"🐺 {t('teammates_suggestions')}", expanded=True):
                for proposal in ai_proposals:
                    target_name = proposal.get("proposed_target_name", proposal.get("proposed_target", ""))
                    wolf_name = proposal.get("werewolf_name", "")
                    reasoning = proposal.get("reasoning", "")
                    st.markdown(f"""
                    **{wolf_name}** {t('suggests_kill')} **{target_name}**
                    > {reasoning}
                    """)
    
    if action_type == "target_selection":
        options: list = [""] + [f"#{t['seat_number']} {t['name']}" for t in valid_targets]
        option_ids: list = [None] + [t["id"] for t in valid_targets]
        
        if allow_skip:
            options.insert(1, f"({t('skip')})")
            option_ids.insert(1, "skip")
        
        selected = st.selectbox(
            t("select_target"),
            options=options,
            key="action_target_select",
        )
        
        if st.button(t("confirm_action"), type="primary", key="confirm_action_btn"):
            idx = options.index(selected) if selected else 0
            target_id = option_ids[idx] if idx > 0 else None
            
            if target_id == "skip":
                logger.info("[App] User chose to skip action")
                session.submit_action("skip", None, None, None)
            else:
                logger.info(f"[App] User selected target: {target_id}")
                session.submit_action(action_type, target_id, None, None)
            
            st.session_state.pending_action = None
            st.session_state.action_submitted = True
            st.success(t("action_submitted"))
            time.sleep(0.5)
            st.rerun()
    
    elif action_type == "yes_no":
        col1, col2 = st.columns(2)
        with col1:
            if st.button(t("yes"), type="primary", use_container_width=True, key="yes_btn"):
                logger.info("[App] User chose: YES")
                session.submit_action(action_type, None, None, True)
                st.session_state.pending_action = None
                st.session_state.action_submitted = True
                st.rerun()
        with col2:
            if st.button(t("no"), use_container_width=True, key="no_btn"):
                logger.info("[App] User chose: NO")
                session.submit_action(action_type, None, None, False)
                st.session_state.pending_action = None
                st.session_state.action_submitted = True
                st.rerun()
    
    elif action_type == "text_input":
        text = st.text_area(
            t("enter_speech"),
            key="speech_input",
            height=100,
        )
        
        if st.button(t("submit"), type="primary", key="submit_text_btn"):
            logger.info(f"[App] User submitted text: {text[:50]}..." if len(text) > 50 else f"[App] User submitted text: {text}")
            session.submit_action(action_type, None, text, None)
            st.session_state.pending_action = None
            st.session_state.action_submitted = True
            st.success(t("action_submitted"))
            time.sleep(0.5)
            st.rerun()


def render_event_log(session: StreamlitGameSession):
    st.subheader(f"📜 {t('game_log')}")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button(t("clear_events"), key="clear_events_btn"):
            session.events.clear()
            st.rerun()
    
    filter_options = {
        "all": t("all"),
        "speech": f"💬 {t('speech')}",
        "vote": f"🗳️ {t('vote')}",
        "death": f"💀 {t('death')}",
        "sheriff": f"👑 {t('sheriff')}",
        "system": f"📢 {t('narration')}",
    }
    
    with col2:
        selected_filter = st.selectbox(
            t("event_filter") if t("event_filter") else "Filter",
            options=list(filter_options.keys()),
            format_func=lambda x: filter_options[x],
            key="event_filter_select",
            label_visibility="collapsed",
        )
    
    events = session.get_events()
    
    if not events:
        st.info(t("no_events"))
        return
    
    def get_event_category(event: EventData) -> str:
        event_type = event.event_type
        # Speech events
        if event_type in ["speech", "last_words", "sheriff_campaign_speech"]:
            return "speech"
        # Vote events
        elif event_type in ["vote_cast", "vote_result", "sheriff_vote"]:
            return "vote"
        # Death events
        elif event_type in ["death_announcement", "lynch", "hunter_shot", "night_kill", 
                           "witch_poison", "wolf_self_explode"]:
            return "death"
        # Sheriff events
        elif event_type in ["sheriff_election", "sheriff_elected", "badge_pass", "badge_tear"]:
            return "sheriff"
        # System/narration events (game lifecycle, actions, resolutions)
        else:
            return "system"
    
    filtered_events = []
    for event in events:
        if selected_filter == "all":
            filtered_events.append(event)
        else:
            category = get_event_category(event)
            if category == selected_filter:
                filtered_events.append(event)
    
    # Use a larger container height for better visibility
    event_container = st.container(height=600)
    
    with event_container:
        display_events = filtered_events[-100:]
        
        last_day = 0
        last_phase = ""
        
        for event in display_events:
            if event.day_number != last_day or event.phase != last_phase:
                if last_day != 0 or last_phase != "":
                    phase_icon = "🌙" if event.phase == "night" else "☀️"
                    phase_text = t("night") if event.phase == "night" else t("day")
                    st.divider()
                    st.markdown(f"**{phase_icon} {t('day')} {event.day_number} - {phase_text}**")
                last_day = event.day_number
                last_phase = event.phase
            
            event_type = event.event_type
            
            if event_type in ["speech", "last_words", "sheriff_campaign_speech"]:
                st.chat_message("user", avatar="🗣️").write(event.description)
            elif event_type in ["death_announcement", "lynch", "hunter_shot", 
                               "night_kill", "witch_poison", "wolf_self_explode"]:
                st.error(event.description)
            elif event_type in ["vote_cast", "vote_result", "sheriff_vote"]:
                st.info(event.description)
            elif event_type in ["sheriff_election", "sheriff_elected", "badge_pass", "badge_tear"]:
                st.warning(event.description)
            else:
                st.write(event.description)


def render_winner_modal(winning_team: str):
    if winning_team == "village":
        st.balloons()
        st.success(f"""
        # 🎉 {t('village_wins')}
        
        {t('good_team_victory')}
        """)
    else:
        st.snow()
        st.error(f"""
        # 🐺 {t('werewolf_wins')}
        
        {t('evil_team_victory')}
        """)
    
    if st.button(t("close") if t("close") else "Close", key="close_winner_btn"):
        st.session_state.show_winner_modal = False
        st.session_state.winner_team = None
        st.rerun()


def render_main_content():
    session = get_session()
    
    if st.session_state.get("show_winner_modal") and st.session_state.get("winner_team"):
        render_winner_modal(st.session_state.winner_team)
        return
    
    if session is None:
        st.title("🐺 " + t("app_title"))
        
        st.markdown(f"""
        ### {t('no_game_running')}
        
        {t('click_start')}
        
        ---
        
        **{t('watch_mode')}**: {t('watch_desc')}
        
        **{t('play_mode')}**: {t('play_desc')}
        """)
        return
    
    if session.mode == "play":
        col1, col2 = st.columns([2, 1])
        
        with col1:
            render_game_arena(session)
            render_event_log(session)
        
        with col2:
            render_human_panel(session)
            render_action_panel(session)
    else:
        col1, col2 = st.columns([3, 2])
        
        with col1:
            render_game_arena(session)
        
        with col2:
            render_event_log(session)
    
    if session.status == "running":
        time.sleep(1)
        st.rerun()


def main():
    init_session_state()
    set_language(st.session_state.ui_language)
    logger.debug("[App] Rendering main UI...")
    
    render_sidebar()
    render_main_content()


if __name__ == "__main__":
    main()
