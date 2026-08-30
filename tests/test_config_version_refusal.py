# Verifies: REQ-d00207-B, REQ-d00212-U, REQ-d00212-V
"""A configuration this elspais does not read is refused where it was written.

An out-of-date file is not upgraded in place. What a project configured is
what it gets, so a file carrying a setting this version does not read -- a
term severity still written flat under ``[terms]``, a severity word that was
retired, a setting nothing reads any more, identifier settings under the
underscore spelling -- is refused, and the refusal names each setting found
and what to write in its place. Rewriting it silently would leave the file
saying one thing and the tool doing another, and the project would have no
way to see which.

The refusal is the whole subject here: there is no migration, so a file's
declared version is a claim the tool checks rather than a starting point it
carries forward.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config import CURRENT_CONFIG_VERSION, load_config

_PROJECT = '[project]\nname = "test"\nnamespace = "REQ"\n'


def _write(tmp_path: Path, body: str, version: int | str | None = CURRENT_CONFIG_VERSION) -> Path:
    """Write a .elspais.toml, optionally without a version line at all."""
    path = tmp_path / ".elspais.toml"
    prefix = ""
    if version is not None:
        rendered = f'"{version}"' if isinstance(version, str) else version
        prefix = f"version = {rendered}\n\n"
    path.write_text(f"{prefix}{_PROJECT}\n{body}", encoding="utf-8")
    return path


# =============================================================================
# The version a file declares
# =============================================================================


class TestDeclaredVersion:
    """REQ-d00207-B: loading is refused where the file is not one this
    elspais reads, and the refusal says which version it found and which it
    needs."""

    # Verifies: REQ-d00207-B
    @pytest.mark.parametrize("declared", [1, 2, 3, 4])
    def test_REQ_d00207_B_an_older_version_is_refused_naming_both_versions(
        self, tmp_path: Path, declared: int
    ) -> None:
        """A file written for an earlier elspais is refused, not migrated.

        The author has to be able to act on the refusal without guessing, so
        it carries both numbers: the version the file declares and the version
        this program reads.
        """
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, "", version=declared))

        message = str(excinfo.value)
        assert f"version = {declared}" in message
        assert f"version {CURRENT_CONFIG_VERSION} configurations" in message
        # And it says what to do once the settings are right.
        assert f"version = {CURRENT_CONFIG_VERSION}" in message.split("Then set:")[-1]

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_an_older_version_with_nothing_to_change_says_so(
        self, tmp_path: Path
    ) -> None:
        """A file whose only fault is its version number is told exactly that.

        Listing no settings at all would read as the refusal having failed to
        inspect the file; saying that nothing has to change is the difference
        between "look again" and "just move the number".
        """
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, "", version=3))

        message = str(excinfo.value)
        assert "No setting in this file has to change." in message
        assert "Settings to change:" not in message

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_a_newer_version_asks_for_a_newer_elspais(self, tmp_path: Path) -> None:
        """A file from a later elspais is a different situation, and gets a
        different answer: there is no edit that makes this program understand
        it, so the refusal points at the program rather than at the file."""
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, "", version=CURRENT_CONFIG_VERSION + 1))

        message = str(excinfo.value)
        assert "Upgrade elspais" in message
        # Nothing is offered as a repair, because nothing here is repairable.
        assert "Settings to change:" not in message
        assert "No setting in this file has to change." not in message

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_a_file_declaring_no_version_loads(self, tmp_path: Path) -> None:
        """Declaring no version is making no claim about the file's shape, and
        is not itself a fault. The settings still decide: this one carries
        nothing the current version fails to read, so it loads."""
        config = load_config(_write(tmp_path, "", version=None))

        assert config["version"] == CURRENT_CONFIG_VERSION
        assert config["project"]["namespace"] == "REQ"

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_a_file_declaring_no_version_is_still_inspected(
        self, tmp_path: Path
    ) -> None:
        """Omitting the version line does not buy past the settings check.

        A file written for an older elspais does not necessarily say so, so
        the settings are what actually catch it.
        """
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, '[terms]\nduplicate_severity = "error"\n', version=None))

        assert "[terms.severity] duplicate" in str(excinfo.value)

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_a_version_that_is_not_a_number_is_refused(self, tmp_path: Path) -> None:
        """A version line that is not a version is reported as that, rather
        than being read as "no version declared" -- the author wrote something
        there and meant it to mean something."""
        with pytest.raises(ValueError, match="is not a version number"):
            load_config(_write(tmp_path, "", version="abc"))


# =============================================================================
# The settings a version no longer reads
# =============================================================================


class TestSettingsThisVersionDoesNotRead:
    """REQ-d00207-B: a setting this version does not read is named where it
    was found, together with the line to write in its place."""

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_a_current_version_file_is_refused_for_its_settings(
        self, tmp_path: Path
    ) -> None:
        """Declaring the current version does not make a stale setting read.

        Accepting the file on the strength of its version line would load a
        configuration whose settings silently do not happen, which is the
        failure the version number was supposed to prevent.
        """
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, '[terms]\nunmarked_severity = "warning"\n'))

        message = str(excinfo.value)
        assert f"carries settings that version {CURRENT_CONFIG_VERSION} does not read" in message

    # Verifies: REQ-d00207-B
    @pytest.mark.parametrize(
        "flat,nested",
        [
            ("duplicate_severity", "duplicate"),
            ("undefined_severity", "undefined"),
            ("unmarked_severity", "unmarked"),
        ],
    )
    def test_REQ_d00207_B_a_flat_term_severity_names_the_nested_key(
        self, tmp_path: Path, flat: str, nested: str
    ) -> None:
        """Term severities are written under ``[terms.severity]`` now, and a
        file still writing one flat under ``[terms]`` is told the key to write
        instead -- with its own value carried across, so the author is reading
        the line they are meant to end up with."""
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, f'[terms]\n{flat} = "error"\n', version=3))

        message = str(excinfo.value)
        assert f'[terms] {flat} = "error"' in message
        assert f'[terms.severity] {nested} = "error"' in message

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_every_flat_term_severity_present_is_named(self, tmp_path: Path) -> None:
        """A file is inspected rather than sampled: each setting it carries is
        named, so one refusal is enough to finish the edit."""
        with pytest.raises(ValueError) as excinfo:
            load_config(
                _write(
                    tmp_path,
                    "[terms]\n"
                    'duplicate_severity = "error"\n'
                    'undefined_severity = "warning"\n'
                    'unmarked_severity = "info"\n',
                    version=3,
                )
            )

        message = str(excinfo.value)
        assert "[terms.severity] duplicate" in message
        assert "[terms.severity] undefined" in message
        assert "[terms.severity] unmarked" in message

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_a_withdrawn_setting_is_named_as_a_line_to_delete(
        self, tmp_path: Path
    ) -> None:
        """``[terms.severity] changed`` was declared, documented, and read by
        nothing, so a project could set it and change no outcome. There is no
        replacement to offer -- the repair is to delete the line."""
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, '[terms.severity]\nchanged = "warning"\n'))

        message = str(excinfo.value)
        assert "[terms.severity] changed" in message
        assert "delete the line" in message
        assert "nothing reads this setting" in message


# =============================================================================
# The retired severity word
# =============================================================================


class TestRetiredSeverityWord:
    """REQ-d00212-U/V: the severity vocabulary is the schema's, and a value
    outside it is refused when the configuration is read."""

    # Verifies: REQ-d00212-V
    @pytest.mark.parametrize(
        "body,setting",
        [
            ('[rules.references]\nmalformed = "ok"\n', "[rules.references] malformed"),
            ('[terms.severity]\nduplicate = "ok"\n', "[terms.severity] duplicate"),
            ('[rules.coverage.tested]\nfull = "ok"\n', "[rules.coverage.tested] full"),
            (
                '[rules.format]\nno_assertions_severity = "ok"\n',
                "[rules.format] no_assertions_severity",
            ),
        ],
        ids=["references", "terms", "coverage-tier", "format"],
    )
    def test_REQ_d00212_V_the_retired_word_is_refused_naming_its_replacement(
        self, tmp_path: Path, body: str, setting: str
    ) -> None:
        """``ok`` named a fifth behaviour -- pass the check but list the
        findings anyway -- that no longer exists. A file writing it is refused
        at the setting that writes it, and told the word to write instead
        rather than left to discover the vocabulary by trial."""
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, body))

        message = str(excinfo.value)
        assert f'{setting} = "ok"' in message
        assert f'{setting} = "off"' in message
        assert "no longer a severity word" in message

    # Verifies: REQ-d00212-U
    def test_REQ_d00212_U_the_refusal_names_the_admitted_vocabulary(self, tmp_path: Path) -> None:
        """The four words the schema admits are stated in the refusal, so the
        author is choosing from the vocabulary rather than guessing at it."""
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, '[rules.references]\nmalformed = "ok"\n'))

        assert "off, info, warning, error" in str(excinfo.value)

    # Verifies: REQ-d00212-V
    def test_REQ_d00212_V_a_word_that_is_not_a_severity_setting_is_not_named(
        self, tmp_path: Path
    ) -> None:
        """Only the enumerated severity settings are inspected.

        A blind walk over the configuration would find any string reading
        "ok" -- a project name, a status word -- and the refusal would demand
        the author change settings that have nothing to do with severity, and
        that are perfectly valid as written.
        """
        path = tmp_path / ".elspais.toml"
        path.write_text(
            f"version = {CURRENT_CONFIG_VERSION}\n\n"
            "[project]\n"
            'name = "ok"\n'
            'namespace = "REQ"\n'
            "\n"
            "[rules.format]\n"
            'status_roles = { active = ["ok"] }\n'
            "\n"
            "[rules.references]\n"
            'malformed = "ok"\n',
            encoding="utf-8",
        )

        with pytest.raises(ValueError) as excinfo:
            load_config(path)

        listed = str(excinfo.value).split("Settings to change:", 1)[1]
        # The one setting that IS a severity is named...
        assert '[rules.references] malformed = "ok"' in listed
        # ...and nothing else is.
        assert "[project]" not in listed
        assert "status_roles" not in listed
        assert listed.count("write instead:") == 1

    # Verifies: REQ-d00212-V
    def test_REQ_d00212_V_a_valid_severity_alongside_a_retired_one_is_untouched(
        self, tmp_path: Path
    ) -> None:
        """The refusal lists what must change and nothing else, so a project
        editing from it does not disturb settings that were already right."""
        with pytest.raises(ValueError) as excinfo:
            load_config(
                _write(
                    tmp_path,
                    '[rules.references]\nmalformed = "ok"\nunknown_requirement = "error"\n',
                )
            )

        message = str(excinfo.value)
        assert "malformed" in message
        assert "unknown_requirement" not in message


# =============================================================================
# Sections that name identifiers
# =============================================================================


class TestRetiredSections:
    """REQ-d00207-B: a section whose settings nothing reads is refused, naming
    the section that is read instead."""

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_underscore_id_patterns_is_refused(self, tmp_path: Path) -> None:
        """Identifier settings are declared under ``[id-patterns]``, with a
        hyphen. The underscore spelling was once accepted alongside it, which
        let one file say the same thing two ways and left a reader to work out
        which the tool had read."""
        with pytest.raises(ValueError) as excinfo:
            load_config(_write(tmp_path, '[id_patterns]\nrequirement = "REQ-{level}{number}"\n'))

        message = str(excinfo.value)
        assert "[id_patterns] is not read" in message
        assert "[id-patterns]" in message

    # Verifies: REQ-d00207-B
    def test_REQ_d00207_B_pre_v2_patterns_section_is_refused(self, tmp_path: Path) -> None:
        """A ``[patterns]`` section is reported, not quietly ignored.

        It was how identifiers were declared before v2. Nothing reads it now,
        so accepting one would load a configuration whose identifier settings
        silently do not happen -- the reader would get the defaults, and the
        spelling the author configured would simply not occur.
        """
        with pytest.raises(ValueError, match=r"\[patterns\]"):
            load_config(
                _write(
                    tmp_path,
                    '[patterns]\nprefix = "PROJ"\n'
                    '[patterns.types]\nprd = { level = 1, id = "p" }\n',
                )
            )
