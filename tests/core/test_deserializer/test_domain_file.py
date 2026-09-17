"""Tests for DomainFile - File/directory deserializer."""

import pytest

from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers.lark import FileDispatcher


@pytest.fixture
def dispatcher(hht_resolver):
    return FileDispatcher(hht_resolver)


class TestDomainFile:
    """Tests for DomainFile deserializer."""

    # Verifies: REQ-o00072-A
    def test_iterate_sources_single_file(self, temp_spec_dir):
        prd_file = temp_spec_dir / "prd.md"
        deserializer = DomainFile(prd_file)

        sources = list(deserializer.iterate_sources())

        assert len(sources) == 1
        ctx, content = sources[0]
        assert ctx.source_type == "file"
        assert "prd.md" in ctx.source_id
        assert "REQ-p00001" in content

    # Verifies: REQ-o00072-A
    def test_iterate_sources_directory(self, temp_spec_dir):
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"])

        sources = list(deserializer.iterate_sources())

        assert len(sources) == 2
        source_ids = [ctx.source_id for ctx, _ in sources]
        assert any("prd.md" in s for s in source_ids)
        assert any("ops.md" in s for s in source_ids)

    # Verifies: REQ-o00072-C
    def test_deserialize_produces_parsed_content(self, temp_spec_dir, dispatcher):
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"])

        results = list(deserializer.dispatch(dispatcher.dispatch_spec))

        # Should have parsed content from both files
        assert len(results) > 0

        # Find requirements
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) >= 2  # At least REQ-p00001 and REQ-p00002

        req_ids = [r.parsed_data["id"] for r in reqs]
        assert "REQ-p00001" in req_ids
        assert "REQ-p00002" in req_ids

    # Verifies: REQ-d00128-D
    def test_deserialize_includes_file_context(self, temp_spec_dir, dispatcher):
        prd_file = temp_spec_dir / "prd.md"
        deserializer = DomainFile(prd_file)

        results = list(deserializer.dispatch(dispatcher.dispatch_spec))

        # All results should have source context
        for result in results:
            assert hasattr(result, "source_context")
            assert "prd.md" in result.source_context.source_id

    # Verifies: REQ-d00212-Y
    def test_skip_dirs_filters_subdirectories(self, temp_spec_dir):
        """Test that skip_dirs excludes files in specified subdirectories."""
        # Create a roadmap subdirectory with a file
        roadmap_dir = temp_spec_dir / "roadmap"
        roadmap_dir.mkdir()
        roadmap_file = roadmap_dir / "future.md"
        roadmap_file.write_text("# Future\n\nSome future content.")

        # Without skip_dirs - should include roadmap file
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"], recursive=True)
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert any("roadmap" in s for s in source_paths), "Should include roadmap without skip"

        # With skip_dirs - should exclude roadmap file
        deserializer = DomainFile(
            temp_spec_dir, patterns=["*.md"], recursive=True, skip_dirs=["roadmap"]
        )
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert not any("roadmap" in s for s in source_paths), "Should exclude roadmap with skip"

    # Verifies: REQ-d00212-Y
    def test_skip_files_filters_specific_files(self, temp_spec_dir):
        """Test that skip_files excludes files with specified names."""
        # Create a README.md file
        readme = temp_spec_dir / "README.md"
        readme.write_text("# README\n\nThis is a readme.")

        # Without skip_files - should include README.md
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"])
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert any("README.md" in s for s in source_paths), "Should include README without skip"

        # With skip_files - should exclude README.md
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"], skip_files=["README.md"])
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert not any("README.md" in s for s in source_paths), "Should exclude README with skip"

    # Verifies: REQ-d00212-Y
    def test_skip_dirs_and_files_combined(self, temp_spec_dir):
        """Test that skip_dirs and skip_files work together."""
        # Create a roadmap subdirectory with files
        roadmap_dir = temp_spec_dir / "roadmap"
        roadmap_dir.mkdir()
        (roadmap_dir / "future.md").write_text("# Future")

        # Create INDEX.md
        (temp_spec_dir / "INDEX.md").write_text("# Index")

        deserializer = DomainFile(
            temp_spec_dir,
            patterns=["*.md"],
            recursive=True,
            skip_dirs=["roadmap"],
            skip_files=["INDEX.md"],
        )
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]

        # Should not contain roadmap or INDEX.md
        assert not any("roadmap" in s for s in source_paths)
        assert not any("INDEX.md" in s for s in source_paths)

        # But should contain the original prd.md and ops.md
        assert any("prd.md" in s for s in source_paths)
        assert any("ops.md" in s for s in source_paths)

    # Verifies: REQ-d00212-Y
    def test_skip_dirs_multi_segment_path(self, temp_spec_dir):
        """Test that skip_dirs supports multi-segment paths like 'regulations/fda'."""
        # Create nested directory: regulations/fda/ with a file
        fda_dir = temp_spec_dir / "regulations" / "fda"
        fda_dir.mkdir(parents=True)
        (fda_dir / "prd-fda.md").write_text("# REQ-p80001: FDA\n\nContent.")

        # Create regulations/other/ which should NOT be skipped
        other_dir = temp_spec_dir / "regulations" / "other"
        other_dir.mkdir(parents=True)
        (other_dir / "prd-other.md").write_text("# REQ-p90001: Other\n\nContent.")

        # skip_dirs with multi-segment path should skip regulations/fda but not regulations/other
        deserializer = DomainFile(
            temp_spec_dir,
            patterns=["*.md"],
            recursive=True,
            skip_dirs=["regulations/fda"],
        )
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]

        assert not any("prd-fda.md" in s for s in source_paths), "Should exclude regulations/fda/"
        assert any("prd-other.md" in s for s in source_paths), "Should include regulations/other/"


class TestDomainFileSelection:
    """One walk decides what is scanned, and it answers in two halves.

    The exclusion half (the ignore configuration, ``skip_dirs``,
    ``skip_files``) removes a file from the walk entirely; the selection half
    (``patterns``) sorts what remains into what this kind reads and what it
    passed over. Nothing else may decide -- REQ-d00212-Q -- and a pattern
    means the same thing wherever it is written (REQ-d00212-W).
    """

    @staticmethod
    def _names(paths, root):
        return {p.relative_to(root).as_posix() for p in paths}

    # Verifies: REQ-d00212-Q, REQ-d00212-W
    def test_selected_and_declined_partition_the_walk(self, tmp_path):
        """Every file reached is either selected or declined, never both."""
        (tmp_path / "keep.md").write_text("# Keep")
        (tmp_path / "notes.txt").write_text("prose")
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "deep.md").write_text("# Deep")
        (tmp_path / "nested" / "data.json").write_text("{}")

        deserializer = DomainFile(tmp_path, patterns=["*.md"], recursive=True)

        selected = self._names(deserializer.iter_selected(), tmp_path)
        declined = self._names(deserializer.iter_declined(), tmp_path)

        assert selected == {"keep.md", "nested/deep.md"}
        assert declined == {"notes.txt", "nested/data.json"}
        assert selected.isdisjoint(declined)
        assert selected | declined == {
            "keep.md",
            "notes.txt",
            "nested/deep.md",
            "nested/data.json",
        }

    # Verifies: REQ-d00212-W
    def test_a_pattern_matches_a_relative_subpath_as_well_as_a_name(self, tmp_path):
        """``api/*.py`` selects within a subdirectory; ``*.py`` selects at any depth.

        Both readings are the one meaning selection has, so a pattern naming a
        directory selects inside the scanned directory rather than being taken
        as a bare name that matches nothing. A path-shaped pattern is anchored
        at the directory being scanned, which is what keeps ``deep/api`` out of
        what ``api/`` names.
        """
        for rel in ("api/one.py", "api/nested/two.py", "other.py", "deep/api/three.py"):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("pass\n")

        by_subpath = DomainFile(tmp_path, patterns=["api/*.py"], recursive=True)
        assert self._names(by_subpath.iter_selected(), tmp_path) == {
            "api/one.py",
            "api/nested/two.py",
        }
        assert self._names(by_subpath.iter_declined(), tmp_path) == {
            "other.py",
            "deep/api/three.py",
        }

        by_name = DomainFile(tmp_path, patterns=["*.py"], recursive=True)
        assert self._names(by_name.iter_selected(), tmp_path) == {
            "api/one.py",
            "api/nested/two.py",
            "other.py",
            "deep/api/three.py",
        }
        assert list(by_name.iter_declined()) == []

    # Verifies: REQ-d00212-Q
    def test_skip_files_is_matched_as_a_glob(self, tmp_path):
        """``*-draft.md`` excludes what it plainly says it excludes.

        Matched by exact name, such an entry excluded nothing at all: no file
        is literally called ``*-draft.md``. The pattern is the only thing that
        changed here, so a name-shaped entry must keep working beside it.
        """
        (tmp_path / "keep.md").write_text("# Keep")
        (tmp_path / "notes-draft.md").write_text("# Draft")
        (tmp_path / "README.md").write_text("# Readme")

        glob_skip = DomainFile(tmp_path, patterns=["*.md"], skip_files=["*-draft.md"])
        assert self._names(glob_skip.iter_selected(), tmp_path) == {"keep.md", "README.md"}
        assert list(glob_skip.iter_declined()) == []

        exact_skip = DomainFile(tmp_path, patterns=["*.md"], skip_files=["README.md"])
        assert self._names(exact_skip.iter_selected(), tmp_path) == {
            "keep.md",
            "notes-draft.md",
        }

    # Verifies: REQ-d00241-G
    def test_an_excluded_file_is_neither_selected_nor_declined(self, tmp_path):
        """A skip pattern removes a file from the walk entirely.

        Declining a file is a thing the caller may report on; skipping one is
        not. A file the project excluded must therefore be absent from both
        halves, whether or not the patterns would have selected it.
        """
        for rel in (
            "src/kept.py",
            "src/notes.txt",
            "src/generated_thing.py",
            "src/generated_thing.txt",
            "src/vendor/lib.py",
        ):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("pass\n")

        deserializer = DomainFile(
            tmp_path / "src",
            patterns=["*.py"],
            recursive=True,
            skip_dirs=["src/vendor"],
            skip_files=["generated_*"],
            repo_root=tmp_path,
        )

        selected = self._names(deserializer.iter_selected(), tmp_path / "src")
        declined = self._names(deserializer.iter_declined(), tmp_path / "src")

        assert selected == {"kept.py"}
        assert declined == {"notes.txt"}
        assert "vendor/lib.py" not in selected | declined
        assert "generated_thing.py" not in selected | declined
        assert "generated_thing.txt" not in selected | declined

    # Verifies: REQ-d00212-Q
    def test_a_directory_pattern_is_read_from_the_repository_root(self, tmp_path):
        """``vendor`` names ``<repo>/vendor``, so it does not reach ``src/vendor``.

        The two spellings are different statements, and this is what makes the
        exact path above say what it means rather than happening to work.
        """
        for rel in ("src/kept.py", "src/vendor/lib.py"):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("pass\n")

        at_root = DomainFile(
            tmp_path / "src",
            patterns=["*.py"],
            recursive=True,
            skip_dirs=["vendor"],
            repo_root=tmp_path,
        )
        assert self._names(at_root.iter_selected(), tmp_path / "src") == {
            "kept.py",
            "vendor/lib.py",
        }

        at_any_depth = DomainFile(
            tmp_path / "src",
            patterns=["*.py"],
            recursive=True,
            skip_dirs=["**/vendor"],
            repo_root=tmp_path,
        )
        assert self._names(at_any_depth.iter_selected(), tmp_path / "src") == {"kept.py"}

    # Verifies: REQ-d00241-G
    def test_an_excluded_file_is_not_read(self, tmp_path):
        """An excluded file never reaches ``iterate_sources`` either.

        The two halves come from one walk, so what the walk drops is dropped
        for every caller -- there is no second path by which a skipped file
        could still be parsed.
        """
        (tmp_path / "kept.py").write_text("# kept\n")
        (tmp_path / "secret.py").write_text("# secret\n")

        deserializer = DomainFile(
            tmp_path,
            patterns=["*.py"],
            recursive=True,
            skip_files=["secret.py"],
            repo_root=tmp_path,
        )

        read = [ctx.source_id for ctx, _ in deserializer.iterate_sources()]
        assert any("kept.py" in source for source in read)
        assert not any("secret.py" in source for source in read)

    # Verifies: REQ-d00212-Q
    def test_a_file_matching_two_patterns_is_selected_once(self, tmp_path):
        """Selection answers a yes/no question, so a file appears once.

        Overlapping patterns are ordinary in a real configuration; a file
        yielded once per matching pattern would be parsed twice and counted
        twice everywhere downstream.
        """
        (tmp_path / "test_thing.py").write_text("def test_thing(): pass\n")

        deserializer = DomainFile(tmp_path, patterns=["test_*.py", "*.py", "*_thing.py"])

        assert len(list(deserializer.iter_selected())) == 1
        assert len(list(deserializer.iterate_sources())) == 1
