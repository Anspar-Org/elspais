"""Tests for the imports:dart dependency source: directives, package resolution and the closure.

Each test writes a small Dart repository under ``tmp_path``: pubspec files
declaring each package's ``path:`` dependencies, and a package configuration
agreeing with them unless the test makes it disagree.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from elspais.graph.dependencies import (
    NoSettings,
    Observation,
    ObservesFrame,
    SourceRequest,
    SourceUnavailable,
    gather_evidence,
    get_source,
    observes_required,
)
from elspais.graph.dependencies.dart_imports import (
    Directive,
    DirectivesUnreadable,
    read_directives,
)


def _write(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _pubspec(root: Path, rel: str, name: str, **sections) -> Path:
    """The pubspec of package *name* at *rel*, holding *sections* as written."""
    return _write(root, f"{rel}/pubspec.yaml", yaml.safe_dump({"name": name, **sections}))


def _package(root: Path, rel: str, name: str, **others: str) -> None:
    """A resolved package at *rel* named *name*; *others* maps package names to root URIs.

    A relative root URI is a repository package, which the pubspec declares as
    a ``path:`` dependency; any other is a hosted package.
    """
    dependencies = {
        other: {"path": uri.removeprefix("../").rstrip("/")} if "://" not in uri else "^1.0.0"
        for other, uri in others.items()
    }
    _pubspec(root, rel, name, **({"dependencies": dependencies} if dependencies else {}))
    _write(root, f"{rel}/pubspec.lock", "packages: {}\n")
    _config(root, rel, {name: "../", **others})


def _config(root: Path, rel: str, packages: dict[str, str], **keys) -> Path:
    entries = [{"name": n, "rootUri": uri, "packageUri": "lib/"} for n, uri in packages.items()]
    data = {"configVersion": 2, "packages": entries, **keys}
    return _write(root, f"{rel}/.dart_tool/package_config.json", json.dumps(data))


def _request(root: Path, *units: str) -> SourceRequest:
    return SourceRequest(
        repo_root=root.resolve(),
        cwd=root.resolve(),
        target_name="dart",
        units=units,
        inputs=frozenset(),
        observed=frozenset(),
        settings=NoSettings(),
        environment_probes=("dart",),
    )


def _evidence(root: Path, *units: str):
    return get_source("imports:dart").evidence(_request(root, *units))


# ---------------------------------------------------------------------------
# The directive reader


# Verifies: REQ-d00333-C
def test_directives_are_read_past_a_script_tag_a_mark_comments_and_annotations():
    text = (
        "﻿#!/usr/bin/env dart\n"
        "// import 'commented.dart';\n"
        "/* import 'block.dart'; /* nested */ import 'still.dart'; */\n"
        "@TestOn('vm')\n"
        "@Tags(<String>['''\n"
        "import 'in_a_string.dart';\n"
        "'''])\n"
        "library a.b;\n"
        "\n"
        "import 'a.dart';\n"
        "export 'package:p/b.dart' show B, C hide D;\n"
        "import 'c' '.dart' as c;\n"
        "import r'raw.dart' deferred as raw;\n"
        "part 'p.dart';\n"
        "\n"
        "class X {}\n"
        "import 'after_a_declaration.dart';\n"
    )
    assert read_directives(text, "//") == (
        Directive("import", ("a.dart",), 10),
        Directive("export", ("package:p/b.dart",), 11),
        Directive("import", ("c.dart",), 12),
        Directive("import", ("raw.dart",), 13),
        Directive("part", ("p.dart",), 14),
    )


# Verifies: REQ-d00333-B
def test_every_branch_of_a_conditional_directive_is_read():
    text = (
        "library;\n"
        "import 'stub.dart'\n"
        "    if (dart.library.io) 'io.dart'\n"
        "    if (dart.library.js_interop == 'true') 'web.dart' as impl;\n"
        "export 'e.dart' if (flag) 'f.dart';\n"
    )
    assert read_directives(text, "//") == (
        Directive("import", ("stub.dart", "io.dart", "web.dart"), 2),
        Directive("export", ("e.dart", "f.dart"), 5),
    )


# Verifies: REQ-d00333-B
def test_part_of_reads_its_library_by_uri_or_by_name():
    assert read_directives("part of '../lib.dart';\nclass A {}\n", "//") == (
        Directive("part of", ("../lib.dart",), 1),
    )
    assert read_directives("part of my.lib;\n", "//") == (Directive("part of", (), 1),)


# Verifies: REQ-d00333-C
@pytest.mark.parametrize(
    ("text", "line", "says"),
    [
        ("import 'a.dart';\n/* open\n", 2, "block comment"),
        ("import 'a$b.dart';\n", 1, "interpolates"),
        ("\nimport 'a\\x41.dart';\n", 2, "escape"),
        ("import a;\n", 1, "not followed by a string literal"),
        ("import 'a.dart' + x;\n", 1, "no name"),
        ("import 'a.dart' if dart 'b.dart';\n", 1, "configuration"),
        ("import 'a.dart'", 1, "no name"),
        ("library;\naugment import 'a.dart';\n", 2, "augmentation"),
        ("@Tags(['a'\nimport 'b.dart';\n", 1, "close"),
    ],
)
def test_directives_that_do_not_read_are_refused_naming_the_line(text, line, says):
    with pytest.raises(DirectivesUnreadable) as caught:
        read_directives(text, "//")
    assert caught.value.line == line
    assert says in caught.value.why


# ---------------------------------------------------------------------------
# Resolution and the closure


def _app(root: Path) -> None:
    """Package ``app`` depending on the repository package ``util``."""
    _package(root, "app", "app", util="../../util/")
    _package(root, "util", "util")


# Verifies: REQ-d00333-B
def test_the_closure_follows_relative_package_export_part_and_conditional_directives(tmp_path):
    repo, cache = tmp_path / "repo", tmp_path / "cache"
    _write(cache, "test/lib/test.dart", "")
    _app(repo)
    _config(
        repo,
        "app",
        {"app": "../", "util": "../../util/", "test": (cache / "test").as_uri() + "/"},
        pubCache=cache.as_uri(),
    )
    _write(
        repo,
        "app/test/a_test.dart",
        "import 'package:test/test.dart';\nimport 'dart:io';\nimport 'helper.dart';\n"
        "import 'package:app/app.dart';\nvoid main() {}\n",
    )
    _write(repo, "app/test/helper.dart", "import '../lib/app.dart';\n")
    _write(
        repo,
        "app/lib/app.dart",
        "export 'src/a.dart';\nexport 'package:util/util.dart';\npart 'src/part.dart';\n",
    )
    _write(repo, "app/lib/src/part.dart", "part of '../app.dart';\n")
    _write(
        repo,
        "app/lib/src/a.dart",
        "import 'stub.dart' if (dart.library.io) 'io.dart' if (dart.library.html) 'web.dart';\n",
    )
    for name in ("stub", "io", "web"):
        _write(repo, f"app/lib/src/{name}.dart", "import 'a.dart';\n")  # a cycle
    _write(repo, "util/lib/util.dart", "")
    _write(repo, "app/lib/unreached.dart", "")

    evidence = _evidence(repo, "app/test/a_test.dart")

    assert evidence.no_evidence == {}
    assert evidence.files["app/test/a_test.dart"] == {
        "app/test/a_test.dart",
        "app/test/helper.dart",
        "app/lib/app.dart",
        "app/lib/src/part.dart",
        "app/lib/src/a.dart",
        "app/lib/src/stub.dart",
        "app/lib/src/io.dart",
        "app/lib/src/web.dart",
        "util/lib/util.dart",
    }


def _hosted(cache: Path, name: str, text: str) -> str:
    """A package *name* in the pub cache whose library file holds *text*; its root URI."""
    _write(cache, f"hosted/{name}/pubspec.yaml", f"name: {name}\n")
    _write(cache, f"hosted/{name}/lib/{name}.dart", text)
    return (cache / "hosted" / name).as_uri() + "/"


# Verifies: REQ-d00333-B
@pytest.mark.parametrize("key", ["pubCache", "flutterRoot"])
def test_a_repository_file_reached_through_the_environment_joins_the_evidence(tmp_path, key):
    repo = tmp_path / "repo"
    cache = tmp_path / "cache"
    x = _hosted(cache, "x", "import 'package:core/core.dart';\nimport 'src/y.dart';\n")
    _write(cache, "hosted/x/lib/src/y.dart", "import 'dart:async';\n")
    _package(repo, "core", "core")
    _write(repo, "core/lib/core.dart")
    # The hosted package x depends on core, which an override places in the repository.
    _pubspec(
        repo,
        "app",
        "app",
        dependencies={"x": "^1.0.0"},
        dependency_overrides={"core": {"path": "../core"}},
    )
    _write(repo, "app/pubspec.lock", "")
    _config(repo, "app", {"app": "../", "x": x, "core": "../../core/"}, **{key: cache.as_uri()})
    _write(repo, "app/test/a_test.dart", "import 'package:x/x.dart';\n")

    evidence = _evidence(repo, "app/test/a_test.dart")

    assert evidence.files == {
        "app/test/a_test.dart": frozenset({"app/test/a_test.dart", "core/lib/core.dart"})
    }


# Verifies: REQ-d00333-B
def test_a_file_of_the_environment_that_does_not_read_leaves_the_units_reaching_it_uncertain(
    tmp_path,
):
    repo = tmp_path / "repo"
    cache = tmp_path / "cache"
    x = _hosted(cache, "x", "import 'unreadable$x.dart';\n")
    _write(repo, "app/pubspec.yaml", "name: app\n")
    _write(repo, "app/pubspec.lock", "")
    _config(repo, "app", {"app": "../", "x": x}, pubCache=cache.as_uri())
    _write(repo, "app/test/a_test.dart", "import 'package:x/x.dart';\n")
    _write(repo, "app/test/b_test.dart", "import 'dart:io';\n")

    evidence = _evidence(repo, "app/test/a_test.dart", "app/test/b_test.dart")

    assert evidence.files == {"app/test/b_test.dart": frozenset({"app/test/b_test.dart"})}
    why = evidence.no_evidence["app/test/a_test.dart"]
    assert str(cache / "hosted" / "x" / "lib" / "x.dart") in why
    assert "interpolates" in why


# Verifies: REQ-d00333-B+D
def test_a_pub_cache_inside_the_repository_is_environment(tmp_path):
    from elspais.utilities.retention import _outside_inputs

    repo = tmp_path / "repo"
    cache = repo / ".ci-pub-cache"
    h = _hosted(cache, "h", "import 'src/i.dart';\n")
    _write(cache, "hosted/h/lib/src/i.dart")
    _write(cache, "hosted/h/hook/build.dart", "import 'package:core/core.dart';\n")
    _package(repo, "core", "core")
    _write(repo, "core/lib/core.dart")
    _pubspec(
        repo,
        "app",
        "app",
        dependencies={"h": "^1.0.0"},
        dependency_overrides={"core": {"path": "../core"}},
    )
    _write(repo, "app/pubspec.lock", "")
    _config(repo, "app", {"app": "../", "h": h, "core": "../../core/"}, pubCache=cache.as_uri())
    _write(repo, "app/test/a_test.dart", "import 'package:h/h.dart';\n")

    evidence = _evidence(repo, "app/test/a_test.dart")

    assert evidence.no_evidence == {}
    assert evidence.files == {"app/test/a_test.dart": frozenset({"app/test/a_test.dart"})}
    assert _outside_inputs(repo, evidence, frozenset({"app/test/a_test.dart"})) == ()


# Verifies: REQ-d00333-B
def test_a_target_with_no_probe_that_affects_retention_has_no_evidence(tmp_path):
    from elspais.graph.dependencies import SourceFailed

    _package(tmp_path, "app", "app")
    _write(tmp_path, "app/test/a_test.dart")
    request = SourceRequest(
        repo_root=tmp_path.resolve(),
        cwd=tmp_path.resolve(),
        target_name="dart",
        units=("app/test/a_test.dart",),
        inputs=frozenset(),
        observed=frozenset(),
        settings=NoSettings(),
    )

    with pytest.raises(SourceFailed) as raised:
        get_source("imports:dart").evidence(request)

    assert "target dart declares no environment probe that affects retention" in str(raised.value)
    assert "flutter --version --machine" in str(raised.value)


# Verifies: REQ-d00333-B
def test_a_package_outside_the_repository_the_cache_and_the_sdk_leaves_its_program_uncertain(
    tmp_path,
):
    repo = tmp_path / "repo"
    sibling = tmp_path / "sibling"
    _write(sibling, "lib/s.dart", "")
    _write(repo, "app/pubspec.yaml", "name: app\n")
    _write(repo, "app/pubspec.lock", "")
    _config(
        repo,
        "app",
        {"app": "../", "s": sibling.as_uri() + "/"},
        pubCache=(tmp_path / "cache").as_uri(),
    )
    _write(repo, "app/test/a_test.dart", "")
    _write(repo, "app/test/b_test.dart", "")

    evidence = _evidence(repo, "app/test/a_test.dart", "app/test/b_test.dart")

    assert evidence.files == {}
    for unit in ("app/test/a_test.dart", "app/test/b_test.dart"):
        assert "package s resolves to" in evidence.no_evidence[unit]
        assert (
            "outside the repository, the pub cache and the Flutter SDK"
            in (evidence.no_evidence[unit])
        )


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("uri", "says"),
    [
        ("package:missing/m.dart", "package missing is not in app/.dart_tool/package_config.json"),
        ("package:util", "names no file of package util"),
        ("package:util/../../app/x.dart", "names no file of package util"),
        ("dart-ext:native", "URI scheme 'dart-ext'"),
        ("http://example.com/a.dart", "URI scheme 'http'"),
        ("../../../outside.dart", "outside the repository"),
    ],
)
def test_a_uri_that_does_not_resolve_leaves_only_the_units_reaching_it_without_evidence(
    tmp_path, uri, says
):
    _app(tmp_path)
    _write(tmp_path, "util/lib/util.dart", "")
    _write(tmp_path, "app/lib/bad.dart", f"import '{uri}';\n")
    _write(tmp_path, "app/test/bad_test.dart", "import '../lib/bad.dart';\n")
    _write(tmp_path, "app/test/good_test.dart", "import 'package:util/util.dart';\n")

    evidence = _evidence(tmp_path, "app/test/bad_test.dart", "app/test/good_test.dart")

    assert set(evidence.files) == {"app/test/good_test.dart"}
    assert says in evidence.no_evidence["app/test/bad_test.dart"]


# Verifies: REQ-d00333-B
def test_a_file_uri_names_a_repository_file(tmp_path):
    _app(tmp_path)
    target = _write(tmp_path, "app/lib/abs.dart", "")
    _write(tmp_path, "app/test/a_test.dart", f"import '{target.resolve().as_uri()}';\n")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert "app/lib/abs.dart" in evidence.files["app/test/a_test.dart"]


# Verifies: REQ-d00333-B
def test_a_missing_or_unreadable_file_leaves_only_the_units_reaching_it_without_evidence(
    tmp_path,
):
    _app(tmp_path)
    _write(tmp_path, "app/test/gen_test.dart", "import '../lib/model.g.dart';\n")
    _write(tmp_path, "app/test/bad_test.dart", "import '../lib/bad.dart';\n")
    (tmp_path / "app/lib").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app/lib/bad.dart").write_bytes(b"\xff\xfe import")
    _write(tmp_path, "app/test/broken_test.dart", "import '../lib/broken.dart';\n")
    _write(tmp_path, "app/lib/broken.dart", "/* never closed\n")
    _write(tmp_path, "app/test/ok_test.dart", "")
    _write(tmp_path, "app/test/data.json", "{}")

    evidence = _evidence(
        tmp_path,
        "app/test/gen_test.dart",
        "app/test/bad_test.dart",
        "app/test/broken_test.dart",
        "app/test/ok_test.dart",
        "app/test/data.json",
    )

    assert set(evidence.files) == {"app/test/ok_test.dart"}
    assert evidence.no_evidence["app/test/gen_test.dart"] == "app/lib/model.g.dart does not exist"
    assert evidence.no_evidence["app/test/bad_test.dart"] == "app/lib/bad.dart is not UTF-8"
    assert evidence.no_evidence["app/test/broken_test.dart"].startswith(
        "app/lib/broken.dart line 1: a block comment does not close"
    )
    assert evidence.no_evidence["app/test/data.json"] == "app/test/data.json is not a Dart file"


# Verifies: REQ-d00333-B
def test_a_part_file_unit_depends_on_its_library_and_one_named_only_by_name_is_uncertain(
    tmp_path,
):
    _app(tmp_path)
    _write(tmp_path, "app/test/suite.dart", "import 'x.dart';\npart 'part_test.dart';\n")
    _write(tmp_path, "app/test/x.dart", "")
    _write(tmp_path, "app/test/part_test.dart", "part of 'suite.dart';\n")
    _write(tmp_path, "app/test/named_test.dart", "part of my.suite;\n")

    evidence = _evidence(tmp_path, "app/test/part_test.dart", "app/test/named_test.dart")

    assert evidence.files["app/test/part_test.dart"] == {
        "app/test/part_test.dart",
        "app/test/suite.dart",
        "app/test/x.dart",
    }
    assert "names only by name" in evidence.no_evidence["app/test/named_test.dart"]


# Verifies: REQ-d00333-B
def test_a_library_is_resolved_with_the_configuration_of_the_test_program(tmp_path):
    # Package b's own configuration maps package:c to c_old; a test of
    # package a imports b, and a's configuration maps package:c to c_new,
    # where a's override places it.
    _package(tmp_path, "a", "a", b="../../b/", c="../../c_new/")
    _pubspec(
        tmp_path,
        "a",
        "a",
        dependencies={"b": {"path": "../b"}},
        dependency_overrides={"c": {"path": "../c_new"}},
    )
    _package(tmp_path, "b", "b", c="../../c_old/")
    _pubspec(tmp_path, "c_new", "c")
    _pubspec(tmp_path, "c_old", "c")
    _write(tmp_path, "b/lib/b.dart", "import 'package:c/c.dart';\n")
    _write(tmp_path, "c_new/lib/c.dart", "")
    _write(tmp_path, "c_old/lib/c.dart", "")
    _write(tmp_path, "a/test/a_test.dart", "import 'package:b/b.dart';\n")

    evidence = _evidence(tmp_path, "a/test/a_test.dart")

    reached = evidence.files["a/test/a_test.dart"]
    assert "c_new/lib/c.dart" in reached
    assert "c_old/lib/c.dart" not in reached


# Verifies: REQ-d00333-B
def test_the_nearest_flutter_test_config_and_each_build_hook_are_roots(tmp_path):
    _app(tmp_path)
    _write(tmp_path, "flutter_test_config.dart", "")  # above the package: never loaded
    _write(tmp_path, "app/flutter_test_config.dart", "import 'lib/golden.dart';\n")
    _write(tmp_path, "app/lib/golden.dart", "")
    _write(tmp_path, "app/test/deep/flutter_test_config.dart", "")
    _write(tmp_path, "app/test/deep/d_test.dart", "")
    _write(tmp_path, "app/test/t_test.dart", "")
    _write(tmp_path, "util/hook/build.dart", "import 'helper.dart';\n")
    _write(tmp_path, "util/hook/helper.dart", "")

    evidence = _evidence(tmp_path, "app/test/deep/d_test.dart", "app/test/t_test.dart")

    hooks = {"util/hook/build.dart", "util/hook/helper.dart"}
    assert (
        evidence.files["app/test/deep/d_test.dart"]
        == {
            "app/test/deep/d_test.dart",
            "app/test/deep/flutter_test_config.dart",
        }
        | hooks
    )
    assert (
        evidence.files["app/test/t_test.dart"]
        == {
            "app/test/t_test.dart",
            "app/flutter_test_config.dart",
            "app/lib/golden.dart",
        }
        | hooks
    )


# ---------------------------------------------------------------------------
# The package configuration


_REMEDY = "run `dart pub get` or `flutter pub get` in app"
_CONFIG_AT = "app/.dart_tool/package_config.json"


# Verifies: REQ-d00333-B
def test_a_pubspec_edit_that_changes_no_resolution_keeps_the_evidence(tmp_path):
    # Pub rewrites the configuration only where its content changes, so a
    # pubspec newer than the configuration is no disagreement.
    _app(tmp_path)
    _write(tmp_path, "util/lib/util.dart", "")
    _write(tmp_path, "app/test/a_test.dart", "import 'package:util/util.dart';\n")
    config = tmp_path / _CONFIG_AT
    os.utime(config, (1_700_000_000, 1_700_000_000))
    pubspec = _pubspec(
        tmp_path,
        "app",
        "app",
        description="A described app.",
        dependencies={"util": {"path": "../util"}},
        flutter={"assets": ["assets/"]},
    )
    assert pubspec.stat().st_mtime > config.stat().st_mtime

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert evidence.no_evidence == {}
    assert evidence.files["app/test/a_test.dart"] == {"app/test/a_test.dart", "util/lib/util.dart"}


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("listed", "says"),
    [
        (
            {"util": "../../other/"},
            f"app/pubspec.yaml declares util at util, which {_CONFIG_AT} places at other",
        ),
        ({}, f"app/pubspec.yaml declares util at util, which {_CONFIG_AT} does not list"),
    ],
)
def test_a_path_dependency_the_configuration_places_elsewhere_or_omits_is_uncertain(
    tmp_path, listed, says
):
    _app(tmp_path)
    _pubspec(tmp_path, "other", "util")
    _config(tmp_path, "app", {"app": "../", **listed})
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert evidence.files == {}
    assert evidence.no_evidence["app/test/a_test.dart"] == f"{says}; {_REMEDY}"


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("listed", "says"),
    [
        ("../../util2/", ""),
        (
            "../../util/",
            f"app/pubspec_overrides.yaml overrides util at util2, which {_CONFIG_AT} places at "
            f"util; {_REMEDY}",
        ),
    ],
)
def test_pubspec_overrides_replace_the_pubspec_overrides_and_must_agree(tmp_path, listed, says):
    _app(tmp_path)
    _pubspec(tmp_path, "util2", "util")
    _pubspec(
        tmp_path,
        "app",
        "app",
        dependencies={"util": "^1.0.0"},
        dependency_overrides={"util": {"path": "../util"}},
    )
    _write(
        tmp_path,
        "app/pubspec_overrides.yaml",
        yaml.safe_dump({"dependency_overrides": {"util": {"path": "../util2"}}}),
    )
    _config(tmp_path, "app", {"app": "../", "util": listed})
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    if says:
        assert evidence.no_evidence["app/test/a_test.dart"] == says
    else:
        assert evidence.no_evidence == {}
        assert "app/test/a_test.dart" in evidence.files


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("listed", "unit", "says"),
    [
        (
            {"ws": "../"},
            "test/ws_test.dart",
            "pubspec.yaml names the workspace member m at pkgs/m, which "
            ".dart_tool/package_config.json does not list",
        ),
        (
            {"ws": "../", "m": "../pkgs/m/", "n": "../pkgs/n/"},
            "pkgs/m/test/m_test.dart",
            ".dart_tool/package_config.json lists n at pkgs/n, which no pubspec of its "
            "program declares",
        ),
    ],
)
def test_a_workspace_member_the_configuration_omits_or_a_former_member_it_lists_is_uncertain(
    tmp_path, listed, unit, says
):
    _pubspec(tmp_path, ".", "ws", workspace=["pkgs/m"])
    _write(tmp_path, "pubspec.lock", "")
    _pubspec(tmp_path, "pkgs/m", "m", resolution="workspace")
    _pubspec(tmp_path, "pkgs/n", "n", resolution="workspace")
    _config(tmp_path, ".", listed)
    _write(tmp_path, unit, "")

    evidence = _evidence(tmp_path, unit)

    assert evidence.files == {}
    assert evidence.no_evidence[unit] == f"{says}; run `dart pub get` or `flutter pub get` in ."


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("section", "uncertain"),
    [("dependencies", True), ("dev_dependencies", False)],
)
def test_a_transitive_path_dependency_must_agree_and_a_dev_dependency_of_one_is_not_read(
    tmp_path, section, uncertain
):
    # Pub reads only the dependencies of a package other than the root.
    _app(tmp_path)
    _pubspec(tmp_path, "util", "util", **{section: {"core": {"path": "../core"}}})
    _pubspec(tmp_path, "core", "core")
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    if uncertain:
        assert evidence.no_evidence["app/test/a_test.dart"] == (
            f"util/pubspec.yaml declares core at core, which {_CONFIG_AT} does not list; {_REMEDY}"
        )
    else:
        assert evidence.no_evidence == {}
        assert "app/test/a_test.dart" in evidence.files


# Verifies: REQ-d00333-B
def test_a_repository_package_the_configuration_lists_and_no_pubspec_declares_is_uncertain(
    tmp_path,
):
    # util was removed from app's pubspec; the configuration still lists it.
    _app(tmp_path)
    _pubspec(tmp_path, "app", "app")
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert evidence.no_evidence["app/test/a_test.dart"] == (
        f"{_CONFIG_AT} lists util at util, which no pubspec of its program declares; {_REMEDY}"
    )


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("pubspec", "says"),
    [
        ("name: app\ndependencies: [\n", "app/pubspec.yaml line 3 does not read as YAML"),
        ("- app\n", "app/pubspec.yaml holds no YAML mapping"),
        (
            "name: app\ndependencies:\n  util: {path: [../util]}\n",
            "app/pubspec.yaml declares util in a form elspais does not read",
        ),
        (
            "name: app\nworkspace: ['pkgs/*']\n",
            "app/pubspec.yaml names workspace members by the pattern pkgs/*, which is not read",
        ),
    ],
)
def test_a_pubspec_that_does_not_read_leaves_its_units_uncertain(tmp_path, pubspec, says):
    _app(tmp_path)
    _write(tmp_path, "app/pubspec.yaml", pubspec)
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert evidence.files == {}
    assert evidence.no_evidence["app/test/a_test.dart"].startswith(says)


# Verifies: REQ-d00333-C
def test_without_pyyaml_the_source_is_unavailable_naming_the_dart_extra(tmp_path, monkeypatch):
    _app(tmp_path)
    _write(tmp_path, "app/test/a_test.dart", "")
    monkeypatch.setitem(sys.modules, "yaml", None)

    with pytest.raises(SourceUnavailable) as raised:
        gather_evidence(get_source("imports:dart"), _request(tmp_path, "app/test/a_test.dart"))

    assert raised.value.extra == "dart"
    assert "elspais[dart]" in str(raised.value)


# Verifies: REQ-d00333-B
def test_a_package_with_no_pubspec_lock_is_uncertain(tmp_path):
    _app(tmp_path)
    (tmp_path / "app/pubspec.lock").unlink()
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert "app holds no pubspec.lock" in evidence.no_evidence["app/test/a_test.dart"]


# Verifies: REQ-d00333-B
@pytest.mark.parametrize(
    ("config_text", "says"),
    [
        ("{not json", "is not a version 2 package configuration"),
        (json.dumps({"configVersion": 1, "packages": []}), "is not a version 2"),
        (json.dumps({"configVersion": 2, "packages": [{"name": "app"}]}), "is not a version 2"),
    ],
)
def test_a_configuration_that_does_not_read_leaves_its_units_uncertain(tmp_path, config_text, says):
    _app(tmp_path)
    _write(tmp_path, "app/.dart_tool/package_config.json", config_text)
    _write(tmp_path, "app/test/a_test.dart", "")

    evidence = _evidence(tmp_path, "app/test/a_test.dart")

    assert says in evidence.no_evidence["app/test/a_test.dart"]


# Verifies: REQ-d00333-B
def test_a_unit_with_no_package_or_whose_package_no_configuration_lists_is_uncertain(tmp_path):
    _app(tmp_path)
    _write(tmp_path, "loose/l_test.dart", "")
    _write(tmp_path, "app/example/pubspec.yaml", "name: example\n")
    _write(tmp_path, "app/example/test/e_test.dart", "")

    evidence = _evidence(tmp_path, "loose/l_test.dart", "app/example/test/e_test.dart")

    assert evidence.files == {}
    assert evidence.no_evidence["loose/l_test.dart"] == (
        "no pubspec.yaml above loose/l_test.dart inside the repository"
    )
    assert evidence.no_evidence["app/example/test/e_test.dart"] == (
        "no package configuration lists the package at app/example; "
        "run `dart pub get` or `flutter pub get` there"
    )


# Verifies: REQ-d00333-B
def test_a_workspace_member_is_resolved_by_the_workspace_root_configuration(tmp_path):
    _write(tmp_path, "pubspec.yaml", "name: ws\nworkspace: [pkgs/m]\n")
    _write(tmp_path, "pubspec.lock", "")
    _write(tmp_path, "pkgs/m/pubspec.yaml", "name: m\nresolution: workspace\n")
    _config(tmp_path, ".", {"ws": "../", "m": "../pkgs/m/"})
    _write(tmp_path, "pkgs/m/lib/m.dart", "")
    _write(tmp_path, "pkgs/m/test/m_test.dart", "import 'package:m/m.dart';\n")

    evidence = _evidence(tmp_path, "pkgs/m/test/m_test.dart")

    assert evidence.files["pkgs/m/test/m_test.dart"] == {
        "pkgs/m/test/m_test.dart",
        "pkgs/m/lib/m.dart",
    }


# ---------------------------------------------------------------------------
# Observation


# Verifies: REQ-d00333-B+C
def test_the_source_observes_only_dart_files_a_test_loads_through_an_import(tmp_path):
    from elspais.utilities.retention import observed_set

    source = get_source("imports:dart")
    assert not observes_required(source)
    inputs = Observation(directories=("apps",), skip_dirs=("**/.dart_tool",))
    test = Observation(directories=("apps/a/test",), file_patterns=("*_test.dart",))
    observation = source.default_observes(ObservesFrame(cwd="apps", inputs=inputs, test=test))
    observed = [
        "apps/a/lib/a.dart",
        "apps/a/lib/src/b.dart",
        "apps/a/example/lib/main.dart",
        "apps/a/hook/build.dart",
        "apps/a/integration_test/flow_test.dart",
        "apps/a/integration_test/robot.dart",
        "apps/a/test/flutter_test_config.dart",
        "apps/a/test/a_test.dart",
    ]
    unobserved = [
        "apps/a/bin/tool.dart",
        "apps/a/tool/gen.dart",
        "apps/a/example/main.dart",
        "apps/a/test/helpers/h.dart",
        "apps/a/test/fixtures/input.dart",
        "apps/a/pubspec.yaml",
        "apps/a/.dart_tool/x.dart",
    ]
    for rel in observed + unobserved:
        _write(tmp_path, rel)

    assert observed_set(tmp_path, observation, observed + unobserved) == frozenset(observed)
