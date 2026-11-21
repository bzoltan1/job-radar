"""Dynamic plugin loader and registry for HTML scrapers."""

import importlib
import inspect
import os
import pkgutil
from typing import Dict, List, Optional, Type

from radar.scrapers.base import BaseHtmlScraper

_SCRAPER_REGISTRY: Dict[str, Type[BaseHtmlScraper]] = {}


def register_scraper(scraper_cls: Type[BaseHtmlScraper]) -> None:
    """Register an HTML scraper class in the global registry."""
    scraper_id = getattr(scraper_cls, "scraper_id", None)
    if scraper_id:
        _SCRAPER_REGISTRY[scraper_id.lower()] = scraper_cls


def discover_scrapers() -> None:
    """Discover and register all scraper plugins in radar.scrapers."""
    _SCRAPER_REGISTRY.clear()
    pkg_dir = os.path.dirname(__file__)
    for _, module_name, is_pkg in pkgutil.iter_modules([pkg_dir]):
        if is_pkg or module_name == "base":
            continue
        try:
            mod = importlib.import_module(f"radar.scrapers.{module_name}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, BaseHtmlScraper) and obj is not BaseHtmlScraper:
                    register_scraper(obj)
        except Exception as e:
            print(f"[-] Failed to load scraper module {module_name}: {e}")


def get_scraper(scraper_id: str) -> Optional[BaseHtmlScraper]:
    """Get an instantiated scraper plugin by its scraper_id."""
    if not _SCRAPER_REGISTRY:
        discover_scrapers()
    cls = _SCRAPER_REGISTRY.get(scraper_id.lower())
    if cls:
        return cls()
    return None


def list_scrapers() -> List[str]:
    """List all registered scraper plugin IDs."""
    if not _SCRAPER_REGISTRY:
        discover_scrapers()
    return sorted(list(_SCRAPER_REGISTRY.keys()))
