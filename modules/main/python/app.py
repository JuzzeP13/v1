"""Application bootstrap that wires all route and socket modules."""

from modules.main.python.core import app, socketio, db_init, init_auth, check_ollama_models, settings

# Register Flask routes
import modules.main.python.routes_main  # noqa: F401
import modules.admin.python.routes_admin  # noqa: F401
import modules.main.python.routes_api  # noqa: F401

# Register Socket.IO handlers
import modules.chat.python.socket_base  # noqa: F401
import modules.chat.python.socket_misc  # noqa: F401


__all__ = [
    "app",
    "socketio",
    "db_init",
    "init_auth",
    "check_ollama_models",
    "settings",
]
