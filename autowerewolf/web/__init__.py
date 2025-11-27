__all__ = ["run_server"]


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    from autowerewolf.web.server import run_server as _run_server
    _run_server(host=host, port=port)
