"""
elspais.config - Configuration loading and defaults
"""

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, load_config, merge_configs

__all__ = [
    "load_config",
    "find_config_file",
    "merge_configs",
    "DEFAULT_CONFIG",
]
