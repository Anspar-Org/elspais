"""Registers the viewer browser fixtures where playwright is installed.

Each test module skips itself when playwright is absent; registering the
fixtures only where it imports keeps that skip from becoming a collection
error here.
"""

import importlib.util

if importlib.util.find_spec("playwright") is not None:
    from .support import (  # noqa: F401
        badge_viewer_url,
        concurrency_viewer_url,
        edit_controls_viewer_url,
        embedded_static_page,
        failing_journey_viewer_url,
        file_mutation_viewer_url,
        page,
        page_badge,
        page_concurrency,
        page_edit_controls,
        page_environments,
        page_file_mutation,
        page_journey,
        page_prefixed,
        page_refused_save,
        page_save_disclosure,
        page_step_binding,
        page_tables,
        prefixed_viewer,
        refused_save_viewer,
        remembering_context,
        save_disclosure_viewer_url,
        second_prefixed_viewer,
        static_viewer_site,
        step_binding_viewer_url,
        viewer_url,
        viewer_url_environments,
        viewer_url_tables,
    )
