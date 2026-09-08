"""Lightweight, safe plugin registry for optional bot capabilities.

Plugins are metadata/lifecycle adapters, not arbitrary code loaded from the network.
Only modules under ``bot.plugins`` are eligible, and disabled plugins never run hooks.
"""
from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Optional


@dataclass(frozen=True)
class PluginSpec:
    name: str
    version: str
    description: str
    module: str = ""
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class PluginState:
    loaded: bool = False
    load_error: str = ""
    started: bool = False
    stopped: bool = False
    loaded_at: float = 0.0


_REGISTRY: Dict[str, PluginSpec] = {}
_STATE: Dict[str, PluginState] = {}
_HOOKS: Dict[str, object] = {}


def _disabled_names() -> set[str]:
    raw = os.getenv("PLUGINS_DISABLED", "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def register(spec: PluginSpec) -> PluginSpec:
    if not spec.name or not spec.name.replace("_", "").isalnum():
        raise ValueError("Invalid plugin name")
    disabled = _disabled_names()
    if spec.name.lower() in disabled:
        spec = PluginSpec(spec.name, spec.version, spec.description, spec.module, False, spec.tags)
    _REGISTRY[spec.name] = spec
    _STATE.setdefault(spec.name, PluginState())
    return spec


def register_builtin_plugins() -> None:
    """Register stable capability boundaries without importing heavy services."""
    specs = (
        PluginSpec("ai", "22.x", "AI providers, routing and context", tags=("core", "ai")),
        PluginSpec("weather", "22.x", "Weather and air-quality features", tags=("feature",)),
        PluginSpec("market", "22.x", "Market and crypto features", tags=("feature",)),
        PluginSpec("media", "22.x", "Image, voice and media AI features", tags=("feature",)),
        PluginSpec("knowledge", "22.x", "Knowledge base and retrieval", tags=("rag",)),
        PluginSpec("agents", "22.x", "Workflow, autonomous and multi-agent execution", tags=("agent",)),
        PluginSpec("automation", "22.x", "Scheduled proactive assistant", tags=("automation",)),
    )
    for spec in specs:
        register(spec)


def is_enabled(name: str) -> bool:
    spec = _REGISTRY.get(name)
    return bool(spec and spec.enabled)


def list_plugins() -> list[dict]:
    return [
        {
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "enabled": spec.enabled,
            "loaded": _STATE.get(spec.name, PluginState()).loaded,
            "started": _STATE.get(spec.name, PluginState()).started,
            "error": _STATE.get(spec.name, PluginState()).load_error,
            "tags": list(spec.tags),
        }
        for spec in sorted(_REGISTRY.values(), key=lambda x: x.name)
    ]


def load_plugin(name: str) -> bool:
    """Load a local plugin module when one is explicitly registered."""
    spec = _REGISTRY.get(name)
    if not spec or not spec.enabled:
        return False
    state = _STATE.setdefault(name, PluginState())
    if state.loaded:
        return True
    if not spec.module:
        state.loaded = True
        state.loaded_at = time.time()
        return True
    try:
        module = importlib.import_module(spec.module)
        _HOOKS[name] = module
        state.loaded = True
        state.loaded_at = time.time()
        return True
    except Exception as exc:
        state.load_error = f"{type(exc).__name__}: {str(exc)[:180]}"
        return False


def load_enabled() -> dict[str, bool]:
    return {name: load_plugin(name) for name, spec in _REGISTRY.items() if spec.enabled}


def _call_hook(name: str, hook: str) -> None:
    module = _HOOKS.get(name)
    fn: Optional[Callable] = getattr(module, hook, None) if module else None
    if fn:
        fn()


def start_enabled() -> None:
    for name, spec in _REGISTRY.items():
        if spec.enabled and load_plugin(name):
            try:
                _call_hook(name, "on_start")
                _STATE[name].started = True
            except Exception as exc:
                _STATE[name].load_error = f"start: {type(exc).__name__}: {str(exc)[:180]}"


def stop_enabled() -> None:
    for name, spec in reversed(list(_REGISTRY.items())):
        if spec.enabled:
            try:
                _call_hook(name, "on_stop")
            except Exception as exc:
                _STATE[name].load_error = f"stop: {type(exc).__name__}: {str(exc)[:180]}"
            _STATE[name].stopped = True


def reset_registry_for_tests() -> None:
    _REGISTRY.clear()
    _STATE.clear()
    _HOOKS.clear()
