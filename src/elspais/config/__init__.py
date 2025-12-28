"""
elspais.config - Configuration loading and defaults
"""

from elspais.config.loader import load_config, find_config_file, merge_configs
from elspais.config.defaults import DEFAULT_CONFIG

__all__ = [
    "load_config",
    "find_config_file",
    "merge_configs",
    "DEFAULT_CONFIG",
]
