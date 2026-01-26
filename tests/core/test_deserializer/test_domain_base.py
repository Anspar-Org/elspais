"""Tests for DomainDeserializer base infrastructure."""

import pytest

from elspais.arch3.Graph.deserializer import (
    DomainContext,
    DomainDeserializer,
)


class TestDomainContext:
    """Tests for DomainContext dataclass."""

    def test_create_minimal(self):
        ctx = DomainContext(source_type="file", source_id="spec/prd.md")
        assert ctx.source_type == "file"
        assert ctx.source_id == "spec/prd.md"
        assert ctx.metadata == {}

    def test_create_with_metadata(self):
        ctx = DomainContext(
            source_type="file",
            source_id="spec/prd.md",
            metadata={"repo": "main"},
        )
        assert ctx.metadata["repo"] == "main"


class TestDomainDeserializerProtocol:
    """Tests for DomainDeserializer protocol."""

    def test_protocol_has_iterate_sources(self):
        assert hasattr(DomainDeserializer, "iterate_sources")

    def test_protocol_has_deserialize(self):
        assert hasattr(DomainDeserializer, "deserialize")
