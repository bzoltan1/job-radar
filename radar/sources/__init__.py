"""Dynamic plugin loader and registry for ATS Sources."""

import importlib
import inspect
import os
import pkgutil
from typing import Dict, List, Optional, Type

from radar.sources.base import BaseSource

_REGISTRY: Dict[str, BaseSource] = {}


def register_source(source_cls: Type[BaseSource]):
    """Instantiate and register a source plugin."""
    instance = source_cls()
    if hasattr(instance, "ats_name") and instance.ats_name:
        _REGISTRY[instance.ats_name.lower()] = instance


def discover_sources():
    """Scan radar/sources/ directory and automatically register BaseSource plugins."""
    _REGISTRY.clear()
    package_dir = os.path.dirname(__file__)
    for _, module_name, is_pkg in pkgutil.iter_modules([package_dir]):
        if is_pkg or module_name == "base":
            continue
        try:
            mod = importlib.import_module(f"radar.sources.{module_name}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, BaseSource) and obj is not BaseSource:
                    register_source(obj)
        except Exception as e:
            print(f"[-] Warning: Failed to load source plugin {module_name}: {e}")

    # Also register any custom HTML scrapers from radar.scrapers
    try:
        from radar.scrapers import discover_scrapers, get_scraper, list_scrapers

        discover_scrapers()
        for scraper_id in list_scrapers():
            if scraper_id not in _REGISTRY:
                scraper = get_scraper(scraper_id)
                if scraper:

                    class _ScraperSourceWrapper(BaseSource):
                        def __init__(self, s, sid):
                            self.scraper = s
                            self.ats_name = sid

                        def fetch(self, target):
                            return self.scraper.scrape(target)

                    _REGISTRY[scraper_id] = _ScraperSourceWrapper(scraper, scraper_id)
    except Exception as e:
        print(f"[-] Warning: Failed to register scraper plugins as sources: {e}")



def get_source(ats_name: str) -> Optional[BaseSource]:
    """Retrieve registered source plugin by ATS name."""
    if not _REGISTRY:
        discover_sources()
    return _REGISTRY.get(ats_name.lower())


def list_sources() -> List[str]:
    """List all registered ATS source names."""
    if not _REGISTRY:
        discover_sources()
    return sorted(list(_REGISTRY.keys()))
