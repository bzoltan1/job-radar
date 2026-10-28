"""Dynamic plugin loader and registry for Output Sinks."""

import importlib
import inspect
import os
import pkgutil
from typing import Dict, List, Optional, Type

from radar.sinks.base import BaseSink

_REGISTRY: Dict[str, BaseSink] = {}


def register_sink(sink_cls: Type[BaseSink]):
    """Instantiate and register a sink plugin."""
    instance = sink_cls()
    if hasattr(instance, "name") and instance.name:
        _REGISTRY[instance.name.lower()] = instance


def discover_sinks():
    """Scan radar/sinks/ directory and automatically register BaseSink plugins."""
    _REGISTRY.clear()
    package_dir = os.path.dirname(__file__)
    for _, module_name, is_pkg in pkgutil.iter_modules([package_dir]):
        if is_pkg or module_name == "base":
            continue
        try:
            mod = importlib.import_module(f"radar.sinks.{module_name}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, BaseSink) and obj is not BaseSink:
                    register_sink(obj)
        except Exception as e:
            print(f"[-] Warning: Failed to load sink plugin {module_name}: {e}")


def get_sink(name: str) -> Optional[BaseSink]:
    """Retrieve registered sink plugin by name."""
    if not _REGISTRY:
        discover_sinks()
    return _REGISTRY.get(name.lower())


def list_sinks() -> List[str]:
    """List all registered sink names."""
    if not _REGISTRY:
        discover_sinks()
    return sorted(list(_REGISTRY.keys()))
