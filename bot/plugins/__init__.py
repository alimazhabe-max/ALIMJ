"""Built-in plugin boundaries for Rooze Ziba."""
from .manager import (
    PluginSpec,
    is_enabled,
    list_plugins,
    load_enabled,
    register,
    register_builtin_plugins,
    start_enabled,
    stop_enabled,
)

__all__ = [
    "PluginSpec", "is_enabled", "list_plugins", "load_enabled",
    "register", "register_builtin_plugins", "start_enabled", "stop_enabled",
]
