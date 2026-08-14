"""`:` is reserved out of every configurable identifier-pattern element.

Validates REQ-p00014-S: the system SHALL reject at configuration-validation
time an identifier-pattern configuration able to produce an identifier or
reference containing the character `:`.

`:` separates the parts of a node identifier -- `file:<namespace>:<path>`
and its `rem:`/`def:` siblings -- and `::` joins a declaring requirement to
a template's in a composite instance ID. A requirement identifier able to
contain one is ambiguous with the graph's own syntax, and the ambiguity
would surface far from the configuration that caused it.

Six configuration elements can put a `:` into a produced identifier: the
assertion separator, the multi-assertion separator, the canonical pattern,
a level letter, an alias template, and the component pattern. The first
four are constrained on the field, so the refusal also reaches the exported
JSON schema; the last two are reached by a model validator, because an
alias value is a mapping entry rather than a field, and a component regex
can admit a colon without containing one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from elspais.config.schema import ElspaisConfig

_SCHEMA_FILE = (
    Path(__file__).resolve().parents[2] / "src" / "elspais" / "config" / "elspais-schema.json"
)


def _payload(**sections) -> dict:
    """A minimal valid configuration, overlaid with the section under test."""
    return {"project": {"name": "x", "namespace": "REQ"}, **sections}


class TestColonRejectedFromEveryPatternElement:
    """Validates REQ-p00014-S: every element that can produce an identifier
    refuses a colon at configuration-validation time."""

    def test_REQ_p00014_S_assertion_separator_with_colon_rejected(self):
        # Verifies: REQ-p00014-S
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(**{"id-patterns": {"assertions": {"separator": ":"}}})
            )
        assert "separator" in str(excinfo.value)

    def test_REQ_p00014_S_multi_separator_with_colon_rejected(self):
        # Verifies: REQ-p00014-S
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(**{"id-patterns": {"assertions": {"multi_separator": ":"}}})
            )
        assert "multi_separator" in str(excinfo.value)

    def test_REQ_p00014_S_canonical_pattern_with_colon_rejected(self):
        # Verifies: REQ-p00014-S
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    **{"id-patterns": {"canonical": "{namespace}:{level.letter}{component}"}}
                )
            )
        assert "canonical" in str(excinfo.value)

    def test_REQ_p00014_S_level_letter_with_colon_rejected(self):
        # Verifies: REQ-p00014-S
        # The letter is interpolated into the canonical pattern, so a colon
        # here reaches every identifier of that level.
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(levels={"prd": {"rank": 1, "letter": "p:", "implements": ["prd"]}})
            )
        assert "letter" in str(excinfo.value)

    def test_REQ_p00014_S_alias_template_with_colon_rejected(self):
        # Verifies: REQ-p00014-S
        # An alias is an accepted reference spelling, so a colon in one
        # produces a reference the graph's own syntax cannot be told from.
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(**{"id-patterns": {"aliases": {"short": "{level.letter}:{component}"}}})
            )
        message = str(excinfo.value)
        assert "aliases.short" in message
        assert "must not contain ':'" in message

    def test_REQ_p00014_S_component_pattern_containing_a_colon_rejected(self):
        # Verifies: REQ-p00014-S
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    **{
                        "id-patterns": {
                            "component": {"style": "regex", "pattern": r"[0-9]{5}:[0-9]{2}"}
                        }
                    }
                )
            )
        assert "admits ':'" in str(excinfo.value)


class TestComponentPatternAdmittingAColon:
    """Validates REQ-p00014-S: what matters is the alphabet the component
    pattern admits, not the characters its text happens to spell."""

    def test_REQ_p00014_S_pattern_admits_colon_without_containing_one_rejected(self):
        # Verifies: REQ-p00014-S
        # `.` matches every printable character, so this pattern produces
        # identifiers containing a colon while containing none itself -- the
        # case a substring check over the pattern text would wave through.
        # The message assertion is load-bearing: this pattern also collides
        # with the default separator (REQ-d00251-F), so a bare rejection
        # would not distinguish the colon guard from that unrelated one.
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(**{"id-patterns": {"component": {"style": "regex", "pattern": "[A-Z].+"}}})
            )
        message = str(excinfo.value)
        assert "admits ':'" in message
        assert "component.pattern" in message


class TestReservationReachesTheExportedSchema:
    """Validates REQ-p00014-S: the field-level constraints are exported, so
    an editor reading the JSON schema refuses what the runtime refuses."""

    @pytest.mark.parametrize(
        "definition,field",
        [
            ("AssertionConfig", "separator"),
            ("AssertionConfig", "multi_separator"),
            ("IdPatternsConfig", "canonical"),
            ("LevelConfig", "letter"),
        ],
    )
    def test_REQ_p00014_S_generated_schema_forbids_a_colon(self, definition, field):
        # Verifies: REQ-p00014-S
        import re

        schema = ElspaisConfig.model_json_schema()
        constraint = schema["$defs"][definition]["properties"][field].get("pattern")
        assert constraint, f"{definition}.{field} exports no pattern constraint"
        assert not re.match(constraint, "a:b"), (
            f"{definition}.{field} exports pattern {constraint!r}, which admits a colon"
        )

    @pytest.mark.parametrize(
        "definition,field",
        [
            ("AssertionConfig", "separator"),
            ("AssertionConfig", "multi_separator"),
            ("IdPatternsConfig", "canonical"),
            ("LevelConfig", "letter"),
        ],
    )
    def test_REQ_p00014_S_committed_schema_file_forbids_a_colon(self, definition, field):
        # Verifies: REQ-p00014-S
        # The committed file is what an editor actually loads.
        import re

        schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
        constraint = schema["$defs"][definition]["properties"][field].get("pattern")
        assert constraint, f"committed schema: {definition}.{field} exports no pattern constraint"
        assert not re.match(constraint, "a:b")


class TestLegalConfigurationsStillLoad:
    """Validates REQ-p00014-S: positive controls -- the reservation refuses
    a colon, not everything."""

    def test_REQ_p00014_S_default_configuration_loads(self):
        # Verifies: REQ-p00014-S
        cfg = ElspaisConfig.model_validate(_payload())
        assert cfg.id_patterns.assertions.separator == "-"
        assert cfg.id_patterns.assertions.multi_separator == "+"
        assert cfg.id_patterns.canonical == "{namespace}-{level.letter}{component}"

    @pytest.mark.parametrize("separator", ["/", ".", "#", "|", "~"])
    def test_REQ_p00014_S_suggested_separators_load(self, separator):
        # Verifies: REQ-p00014-S
        # These are the separators the schema offers when the default one is
        # taken; every one of them must survive the colon reservation.
        cfg = ElspaisConfig.model_validate(
            _payload(**{"id-patterns": {"assertions": {"separator": separator}}})
        )
        assert cfg.id_patterns.assertions.separator == separator

    @pytest.mark.parametrize("multi_separator", ["/", ".", "#", "|", "~"])
    def test_REQ_p00014_S_suggested_multi_separators_load(self, multi_separator):
        # Verifies: REQ-p00014-S
        cfg = ElspaisConfig.model_validate(
            _payload(**{"id-patterns": {"assertions": {"multi_separator": multi_separator}}})
        )
        assert cfg.id_patterns.assertions.multi_separator == multi_separator

    def test_REQ_p00014_S_component_pattern_without_a_colon_loads(self):
        # Verifies: REQ-p00014-S
        # The alphabet check must not over-fire: this pattern admits digits
        # only, and is accepted unchanged.
        cfg = ElspaisConfig.model_validate(
            _payload(**{"id-patterns": {"component": {"style": "regex", "pattern": r"[0-9]{5,}"}}})
        )
        assert cfg.id_patterns.component.pattern == r"[0-9]{5,}"

    def test_REQ_p00014_S_colon_free_aliases_and_letters_load(self):
        # Verifies: REQ-p00014-S
        cfg = ElspaisConfig.model_validate(
            _payload(
                **{
                    "id-patterns": {"aliases": {"short": "{level.letter}{component}"}},
                    "levels": {"prd": {"rank": 1, "letter": "p", "implements": ["prd"]}},
                }
            )
        )
        assert cfg.id_patterns.aliases["short"] == "{level.letter}{component}"
        assert cfg.levels["prd"].letter == "p"
