from typing import TYPE_CHECKING

from autowerewolf.config.models import ModelBackend, ModelConfig

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


def get_chat_model(config: ModelConfig) -> "BaseChatModel":
    if config.backend == ModelBackend.OLLAMA:
        return _get_ollama_model(config)
    elif config.backend == ModelBackend.API:
        return _get_api_model(config)
    else:
        raise ValueError(f"Unsupported backend: {config.backend}")


def _get_ollama_model(config: ModelConfig) -> "BaseChatModel":
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        raise ImportError(
            "langchain-ollama is required for Ollama backend. "
            "Install with: pip install langchain-ollama"
        )

    kwargs = {
        "model": config.model_name,
        "temperature": config.temperature,
        "num_predict": config.max_tokens,
    }

    if config.ollama_base_url:
        kwargs["base_url"] = config.ollama_base_url

    if config.top_p is not None:
        kwargs["top_p"] = config.top_p

    if config.top_k is not None:
        kwargs["top_k"] = config.top_k

    if config.repeat_penalty is not None:
        kwargs["repeat_penalty"] = config.repeat_penalty

    if config.seed is not None:
        kwargs["seed"] = config.seed

    if config.stop_sequences:
        kwargs["stop"] = config.stop_sequences

    if config.extra_params:
        kwargs.update(config.extra_params)

    return ChatOllama(**kwargs)


def _get_api_model(config: ModelConfig) -> "BaseChatModel":
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        try:
            from langchain_community.chat_models import ChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai or langchain-community is required for API backend. "
                "Install with: pip install langchain-openai"
            )

    kwargs = {
        "model": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "request_timeout": config.timeout_s,
    }

    if config.api_key:
        kwargs["api_key"] = config.api_key

    if config.api_base:
        kwargs["base_url"] = config.api_base

    if config.top_p is not None:
        kwargs["top_p"] = config.top_p

    if config.seed is not None:
        kwargs["seed"] = config.seed

    if config.stop_sequences:
        kwargs["stop"] = config.stop_sequences

    if config.extra_params:
        kwargs["model_kwargs"] = config.extra_params

    return ChatOpenAI(**kwargs)
