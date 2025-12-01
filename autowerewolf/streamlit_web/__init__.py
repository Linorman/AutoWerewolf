"""Streamlit Web UI for AutoWerewolf."""

from autowerewolf.streamlit_web.i18n import t, set_language, get_all_translations
from autowerewolf.streamlit_web.config_loader import streamlit_config_loader

__all__ = ["t", "set_language", "get_all_translations", "streamlit_config_loader"]
