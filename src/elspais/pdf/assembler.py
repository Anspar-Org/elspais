# Implements: REQ-p00080-B, REQ-p00080-C, REQ-p00080-D, REQ-p00080-E, REQ-p00080-F
# Implements: REQ-p00080-H, REQ-p00080-I, REQ-p00080-J, REQ-p00080-K
"""Markdown assembler for PDF compilation.

Uses the graph for file ordering metadata (level, depth), then reads the
source spec files directly to preserve all content faithfully.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.utilities.patterns import IdResolver, build_resolver


def _build_level_metadata(
    config: dict | None,
) -> tuple[dict[str, int], dict[str, str], re.Pattern[str]]:
    """Return (order, headings, prefix_re) derived from `[levels]` config.

    Order: uppercase level key -> rank.
    Headings: uppercase level key -> display_name + " Requirements" fallback.
    prefix_re: regex matching `<level_key>-` or numeric prefix at filename start.

    Falls back to the schema's default `[levels]` block (via
    `elspais.config.config_defaults()`) when no config is passed, so the
    fallback table is the single source of truth from the pydantic schema.
    """
    from elspais.config import config_defaults

    levels_cfg = (config or {}).get("levels") if config else None
    if not isinstance(levels_cfg, dict) or not levels_cfg:
        levels_cfg = config_defaults().get("levels") or {}

    order: dict[str, int] = {}
    headings: dict[str, str] = {}
    keys: list[str] = []
    for key, entry in levels_cfg.items():
        rank = (entry or {}).get("rank") if isinstance(entry, dict) else None
        if rank is None:
            continue
        upper = key.upper()
        order[upper] = int(rank)
        display = (entry or {}).get("display_name") if isinstance(entry, dict) else None
        headings[upper] = f"{display or key.title()} Requirements"
        keys.append(re.escape(key.lower()))

    if not keys:
        # Final defensive fallback: numeric prefixes only.
        return order, headings, re.compile(r"^\d+-?", re.IGNORECASE)

    alt = "|".join(keys)
    prefix_re = re.compile(rf"^(?:{alt}|\d+)-?", re.IGNORECASE)
    return order, headings, prefix_re


# Matches requirement heading lines at any heading level: # REQ-xxx or ## REQ-xxx
_REQ_HEADING_RE = re.compile(r"^(#{1,3})\s+(REQ-\S+)")

# Matches footer lines: *End* *Title* | **Hash**: ...
_FOOTER_RE = re.compile(r"^\*End\*")

# Matches Markdown image references to .mmd files: ![alt](path.mmd)
_MMD_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+\.mmd)(\))")

# Matches Markdown image references to raster/vector image files with an
# optional quoted title: ![alt](path.png), ![alt](img/x.jpg "caption").
# .mmd references are handled separately by _MMD_IMAGE_RE.
_IMAGE_REF_RE = re.compile(
    r"(!\[[^\]]*\]\()([^)\s]+\.(?:png|jpe?g|gif|svg))((?:\s+\"[^\"]*\")?\))",
    re.IGNORECASE,
)

# Opening or closing marker of a fenced code block (``` or ~~~).
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

# A line indented far enough to open or continue an indented code block.
_INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")

# A Markdown list item marker, whose indented continuation lines are list
# content rather than code.
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")

log = logging.getLogger(__name__)


# Implements: REQ-p00080-I, REQ-p00080-J
@dataclass(frozen=True)
class AssemblyDiagnostic:
    """Referenced content the assembler could not place in the document.

    A compiled document that quietly comes out short an image, a diagram,
    or an entire repository's spec file is indistinguishable from a
    correct one. Each such omission is recorded here so the caller can
    disclose it instead of shipping a silently degraded document.
    """

    kind: str
    """What was omitted or could not be analysed: ``image``, ``diagram``,
    ``source-file``, ``repository``, or ``code-fence``."""

    reference: str
    """The reference exactly as written in the source, or the file path."""

    source_file: str
    """Repo-relative spec file declaring the reference; ``""`` when the
    omitted thing *is* the file."""

    repo: str
    """Name of the repository the reference was resolved against."""

    searched: tuple[str, ...]
    """Absolute locations tried, in the order they were tried."""

    cause: str
    """Why resolution failed."""

    remedy: str
    """The action available to the caller."""

    def format(self) -> str:
        """Render the diagnostic as one human-readable block.

        Names the operation, the cause, and the remedial action, so a
        reader of the compile log can act without re-deriving any of it.
        """
        where = f" declared in {self.source_file}" if self.source_file else ""
        repo = f" [repo: {self.repo}]" if self.repo else ""
        lines = [f"  {self.kind} reference '{self.reference}'{where}{repo}"]
        lines.append(f"    cause: {self.cause}")
        if self.searched:
            lines.append(f"    searched: {', '.join(self.searched)}")
        lines.append(f"    remedy: {self.remedy}")
        return "\n".join(lines)


class MarkdownAssembler:
    """Assembles structured Markdown from spec files.

    Uses the graph only for metadata: which files contain requirements,
    what level they belong to, and how to order them by graph depth.
    Content comes directly from the source spec files.
    """

    def __init__(
        self,
        graph: FederatedGraph,
        title: str | None = None,
        overview: bool = False,
        max_depth: int | None = None,
        resolver: IdResolver | None = None,
        config: dict | None = None,
    ) -> None:
        self._graph = graph
        self._overview = overview
        self._max_depth = max_depth
        if title:
            self._title = title
        elif overview:
            self._title = "Product Requirements Overview"
        else:
            self._title = "Requirements Specification"
        if resolver is None:
            # An empty dict is not the default configuration: it declares no
            # levels, so the grammar it yields matches no identifier.
            from elspais.config import config_defaults

            resolver = build_resolver(config_defaults())
        self._resolver = resolver
        order, headings, prefix_re = _build_level_metadata(config)
        self._level_order = order
        self._level_headings = headings
        self._level_prefix_re = prefix_re
        self._diagnostics: list[AssemblyDiagnostic] = []
        self._seen_diagnostics: set[tuple[str, str, str]] = set()
        self._resource_roots: list[Path] | None = None

    # ------------------------------------------------------------------
    # Degradation reporting
    # ------------------------------------------------------------------

    # Implements: REQ-p00080-I, REQ-p00080-J
    def iter_diagnostics(self) -> Iterator[AssemblyDiagnostic]:
        """Iterate content the assembly could not place, in discovery order."""
        yield from self._diagnostics

    # Implements: REQ-p00080-K
    def diagnostic_count(self) -> int:
        """Number of distinct omissions recorded during assembly."""
        return len(self._diagnostics)

    def _record_diagnostic(self, diagnostic: AssemblyDiagnostic) -> None:
        """Record an omission once per (kind, reference, declaring file)."""
        key = (diagnostic.kind, diagnostic.reference, diagnostic.source_file)
        if key in self._seen_diagnostics:
            return
        self._seen_diagnostics.add(key)
        self._diagnostics.append(diagnostic)

    # Implements: REQ-p00080-H
    def resource_roots(self) -> list[Path]:
        """Directories that may satisfy a relative reference, in search order.

        Each federated repo contributes its root and its ``spec/``
        directory. This is the single definition of that set: the pdf
        command hands it to pandoc as ``--resource-path``, and the
        reference resolvers probe it before declaring a reference
        unresolvable, so the two surfaces cannot disagree about what
        "not found" means.
        """
        if self._resource_roots is None:
            roots: list[Path] = []
            seen: set[Path] = set()
            for entry in self._graph.iter_repos():
                for candidate in (entry.repo_root, entry.repo_root / "spec"):
                    resolved = candidate.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        roots.append(resolved)
            self._resource_roots = roots
        return list(self._resource_roots)

    def _reachable_via_resource_root(self, reference: str) -> bool:
        """Whether pandoc's ``--resource-path`` would find this reference.

        Probes the percent-decoded form, which is what pandoc resolves.
        """
        decoded = unquote(reference)
        return any((root / decoded).exists() for root in self.resource_roots())

    def _repo_name_for_root(self, repo_root: Path | None) -> str:
        """Name the federated repo owning ``repo_root``, best effort."""
        if repo_root is None:
            return self._graph.root_repo_name
        for entry in self._graph.iter_repos():
            if entry.repo_root == repo_root:
                return entry.name
        return self._graph.root_repo_name

    def assemble(self) -> str:
        """Assemble the complete Markdown document.

        Returns:
            Structured Markdown string ready for Pandoc.
        """
        parts: list[str] = []

        self._record_unloadable_repos()

        # YAML metadata header for Pandoc
        from elspais.utilities.report_meta import report_metadata

        meta = report_metadata()
        parts.append("---")
        parts.append(f'title: "{self._title}"')
        parts.append(f'subtitle: "elspais {meta["version"]}, {meta["date"]}, {meta["source"]}"')
        parts.append("toc: true")
        parts.append("toc-depth: 2")
        parts.append("---")
        parts.append("")

        # Group requirements by file, then partition by level
        file_groups = self._group_by_file()
        # Map each file path to its owning repo (root or associate). Files
        # whose nodes span multiple repos are extraordinarily rare; the
        # first node wins (matches _group_by_file's document order).
        file_owners: dict[str, str] = {}
        for fp, nodes in file_groups.items():
            for node in nodes:
                try:
                    file_owners[fp] = self._graph.repo_for(node.id).name
                    break
                except KeyError:
                    continue
        level_buckets = self._partition_by_level(file_groups)

        # Emit each level group
        if self._overview:
            levels_to_emit = ("PRD",)
        else:
            levels_to_emit = ("PRD", "OPS", "DEV")

        for level in levels_to_emit:
            files = level_buckets.get(level, [])
            if not files:
                continue

            # Apply max_depth filter for core files in overview mode
            if self._overview and self._max_depth is not None:
                files = self._filter_by_depth(files, file_groups)

            if not files:
                continue

            heading = self._level_headings.get(level, level)
            parts.append(f"# {heading}")
            parts.append("")

            # Sort files within level by graph depth, then alphabetically
            sorted_files = self._sort_files_by_depth(files, file_groups)

            for file_path in sorted_files:
                owner_root = self._repo_root_for_owner(file_owners.get(file_path))
                parts.extend(self._render_file(file_path, owning_repo_root=owner_root))

        # Topic index — scope to rendered files only in overview mode
        if self._overview:
            rendered_files: set[str] = set()
            for level in levels_to_emit:
                bucket = level_buckets.get(level, [])
                if self._max_depth is not None:
                    bucket = self._filter_by_depth(bucket, file_groups)
                rendered_files.update(bucket)
            index_groups = {k: v for k, v in file_groups.items() if k in rendered_files}
        else:
            index_groups = file_groups
        index_section = self._build_topic_index(index_groups, file_owners=file_owners)
        if index_section:
            parts.append("# Topic Index")
            parts.append("")
            parts.extend(index_section)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # File rendering — reads source files directly
    # ------------------------------------------------------------------

    def _render_file(self, file_path: str, owning_repo_root: Path | None = None) -> list[str]:
        """Render a spec file's content with adjusted heading levels.

        Reads the file directly. Detects the heading level used for requirements
        in this file (e.g., `#` or `##`), then adjusts all headings so that:
        - File title → `##`
        - Requirement headings → `###` with anchor and page break
        - Sub-sections within requirements → `####`
        - `---` separators and `*End*` footer lines → stripped

        ``owning_repo_root`` anchors path resolution to the file's owning
        associate when supplied (cross-repo PDF rendering).
        """
        resolved, searched = self._resolve_path_candidates(
            file_path, owning_repo_root=owning_repo_root
        )
        if not resolved or not resolved.exists():
            self._record_unreadable_source_file(file_path, owning_repo_root, searched)
            return []

        source = resolved.read_text(encoding="utf-8")
        # Strip control characters that break LaTeX (keep \n \r \t)
        source = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", source)
        source_lines = source.split("\n")

        seen_file_title = False
        fence: str | None = None
        indented_code = False
        prev_blank = True
        in_list = False

        lines: list[str] = ["\\newpage", ""]
        for line in source_lines:
            # Code blocks pass through byte-for-byte. A reference inside a
            # code sample is text about a reference, not a reference:
            # rewriting it corrupts the sample, and reporting it as
            # unresolvable claims an omission the document never suffered.
            marker = _FENCE_RE.match(line)
            if fence is not None:
                if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                    fence = None
                lines.append(line)
                continue
            if marker:
                fence = marker.group(1)
                lines.append(line)
                continue

            blank = not line.strip()
            indented = _INDENTED_CODE_RE.match(line) is not None

            # A CommonMark indented code block opens on a 4-space (or tab)
            # indent that follows a blank line and does not continue a
            # paragraph. List continuation is indented the same way but is
            # list content, so an open list suppresses the reading.
            if indented_code:
                if not blank and not indented:
                    indented_code = False
            elif indented and prev_blank and not in_list:
                indented_code = True

            if not blank:
                if not indented:
                    in_list = _LIST_ITEM_RE.match(line) is not None
                prev_blank = False
            else:
                prev_blank = True

            if indented_code:
                lines.append(line)
                continue

            # Strip horizontal rules (requirement separators)
            if line.strip() == "---":
                continue

            # Requirement heading → \newpage + ### with anchor
            req_match = _REQ_HEADING_RE.match(line)
            if req_match:
                hashes = req_match.group(1)
                req_id = req_match.group(2).rstrip(":")
                rest = line[len(hashes) + 1 :]
                lines.append("\\newpage")
                lines.append("")
                lines.append(f"### {rest} {{#{req_id}}}")
                continue

            # Other headings
            if line.startswith("#"):
                text = line.lstrip("#").lstrip()
                if not seen_file_title:
                    # First heading in the file → section (appears in TOC)
                    lines.append(f"## {text}")
                    seen_file_title = True
                else:
                    # All other non-requirement headings → excluded from TOC
                    lines.append(f"#### {text}")
                continue

            # Replace .mmd image references with .png
            if ".mmd)" in line:
                line = self._resolve_mermaid_images(
                    line, file_path, owning_repo_root=owning_repo_root
                )

            # Rewrite relative raster/vector image references to absolute
            # paths anchored at the owning repo (TOOL-31).
            if "![" in line:
                line = self._resolve_image_paths(line, file_path, owning_repo_root=owning_repo_root)

            # Ensure blank line before first list item so Pandoc renders as a list
            stripped = line.lstrip()
            if (
                stripped.startswith("- ")
                and lines
                and lines[-1].strip()
                and not lines[-1].lstrip().startswith("- ")
            ):
                lines.append("")

            lines.append(line)

        if fence is not None:
            # Everything after the unclosed marker was treated as code, so
            # requirement headings and end markers past that point were
            # never processed. The document is degraded in a way no
            # reference-level check can see; say so.
            # Implements: REQ-p00080-I
            self._record_diagnostic(
                AssemblyDiagnostic(
                    kind="code-fence",
                    reference=file_path,
                    source_file=file_path,
                    repo=self._repo_name_for_root(owning_repo_root),
                    searched=(),
                    cause=(
                        "A code fence is opened and never closed; the rest of "
                        "the file was treated as code, so any requirement "
                        "structure after it is not rendered as structure."
                    ),
                    remedy="Close the code fence in the spec file.",
                )
            )

        # Trim trailing blank lines
        while lines and not lines[-1].strip():
            lines.pop()
        lines.append("")

        return lines

    @staticmethod
    def _detect_req_heading_level(source_lines: list[str]) -> int:
        """Detect the Markdown heading level used for requirements in a file.

        Returns the number of '#' characters (1 for `#`, 2 for `##`, etc.).
        Defaults to 1 if no requirement headings found.
        """
        for line in source_lines:
            m = _REQ_HEADING_RE.match(line)
            if m:
                return len(m.group(1))
        return 1

    def _repo_root_for_owner(self, owner_name: str | None) -> Path | None:
        """Look up the on-disk root for a named federated repo, if any."""
        if not owner_name:
            return None
        for entry in self._graph.iter_repos():
            if entry.name == owner_name:
                return entry.repo_root
        return None

    def _resolve_path(self, file_path: str, owning_repo_root: Path | None = None) -> Path | None:
        """Resolve a source path to an absolute Path.

        When ``owning_repo_root`` is supplied, the file is resolved
        against that repo root first (the federated case for cross-repo
        files). Falls back to ``self._graph.repo_root`` and then to a
        scan of every repo in ``iter_repos()`` so that cross-repo
        references render even when the caller didn't track ownership.
        """
        resolved, _searched = self._resolve_path_candidates(
            file_path, owning_repo_root=owning_repo_root
        )
        return resolved

    def _resolve_path_candidates(
        self,
        file_path: str,
        owning_repo_root: Path | None = None,
    ) -> tuple[Path | None, list[Path]]:
        """Resolve a source path, also returning every location tried.

        Callers that must report a failure need the candidate list, and
        deriving it twice would let the report drift from the search.
        """
        searched: list[Path] = []
        p = Path(file_path)
        if p.is_absolute():
            searched.append(p)
            if p.exists():
                return p, searched
        if owning_repo_root is not None:
            candidate = owning_repo_root / file_path
            searched.append(candidate)
            if candidate.exists():
                return candidate, searched
        # Try relative to root repo
        candidate = self._graph.repo_root / file_path
        if candidate not in searched:
            searched.append(candidate)
            if candidate.exists():
                return candidate, searched
        # Fall back: search every federated repo (cross-repo file with
        # no ownership context — rare in normal callers but needed for
        # mermaid blocks emitted from preamble-style global text).
        for entry in self._graph.iter_repos():
            candidate = entry.repo_root / file_path
            if candidate in searched:
                continue
            searched.append(candidate)
            if candidate.exists():
                return candidate, searched
        return None, searched

    # Implements: REQ-p00080-J
    def _record_unreadable_source_file(
        self,
        file_path: str,
        owning_repo_root: Path | None,
        searched: list[Path],
    ) -> None:
        """Record a spec file whose content could not be read.

        A file that cannot be located takes every requirement, assertion
        and rationale it holds out of the document. Dropping a whole
        repository's content without saying so is the omission
        REQ-p00080's REQ-p00019 instance prohibits.
        """
        self._record_diagnostic(
            AssemblyDiagnostic(
                kind="source-file",
                reference=file_path,
                source_file="",
                repo=self._repo_name_for_root(owning_repo_root),
                searched=tuple(str(p) for p in searched),
                cause=(
                    "Spec file not found in its owning repository; every "
                    "requirement it holds is absent from the document."
                ),
                remedy=("Restore the file, or update the requirement's source location."),
            )
        )

    # Implements: REQ-p00080-J
    def _record_unloadable_repos(self) -> None:
        """Record configured repositories that contributed nothing.

        A federated repository whose configured path does not resolve
        loads no graph at all, so none of its requirements reach the
        document and no per-file check can notice: there are no files to
        fail on. The absent repository is the omission, and it is
        reported as one.
        """
        root_name = self._graph.root_repo_name
        for entry in self._graph.iter_repos():
            if entry.name == root_name or entry.graph is not None:
                continue
            self._record_diagnostic(
                AssemblyDiagnostic(
                    kind="repository",
                    reference=entry.name,
                    source_file="",
                    repo=entry.name,
                    searched=(str(entry.repo_root),),
                    cause=(
                        "Associate repository could not be loaded; none of "
                        "its requirements are in the document."
                    ),
                    remedy=(
                        "Correct the associate's configured path, or remove "
                        "the associate from the configuration."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Mermaid diagram resolution
    # ------------------------------------------------------------------

    def _resolve_mermaid_images(
        self,
        line: str,
        source_file: str,
        owning_repo_root: Path | None = None,
    ) -> str:
        """Replace .mmd image references with .png equivalents.

        For each ![alt](path.mmd) reference:
        1. Look for path.png alongside the .mmd file
        2. If not found, generate it using mmdc (mermaid CLI)
        3. Replace the reference with the absolute .png path

        ``owning_repo_root`` anchors resolution to the source file's
        owning repo when known (federated cross-repo rendering). A
        diagram that cannot be located, or that cannot be rendered
        because ``mmdc`` is absent or failed, is recorded as a
        diagnostic rather than dropped without a word.
        """
        anchor = owning_repo_root if owning_repo_root is not None else self._graph.repo_root

        def _replace_mmd(match: re.Match) -> str:
            prefix = match.group(1)  # ![alt](
            mmd_path = match.group(2)  # relative/path.mmd
            suffix = match.group(3)  # )

            # Resolve .mmd path relative to the source file's directory
            decoded = unquote(mmd_path)
            source_dir = Path(source_file).parent
            searched: list[Path] = [(anchor / source_dir / decoded).resolve()]
            mmd_resolved = anchor / source_dir / decoded
            if not mmd_resolved.exists():
                # Try relative to anchor repo root
                mmd_resolved = anchor / decoded
                searched.append((anchor / decoded).resolve())
            if not mmd_resolved.exists():
                self._record_unresolved_reference(
                    kind="diagram",
                    reference=mmd_path,
                    source_file=source_file,
                    owning_repo_root=owning_repo_root,
                    searched=searched,
                )
                return match.group(0)  # Leave unchanged

            png_path = mmd_resolved.with_suffix(".png")

            # Use existing .png if available
            if not png_path.exists():
                png_path = self._generate_mermaid_png(mmd_resolved, png_path)
                if png_path is None:
                    self._record_diagnostic(
                        AssemblyDiagnostic(
                            kind="diagram",
                            reference=mmd_path,
                            source_file=source_file,
                            repo=self._repo_name_for_root(owning_repo_root),
                            searched=(str(mmd_resolved),),
                            cause=(
                                "Mermaid source found but could not be rendered "
                                "to an image (mmdc missing or failed)."
                            ),
                            remedy=(
                                "Install the mermaid CLI (mmdc), or commit a "
                                "pre-rendered .png alongside the .mmd source."
                            ),
                        )
                    )
                    return match.group(0)

            return f"{prefix}{png_path}{suffix}"

        return _MMD_IMAGE_RE.sub(_replace_mmd, line)

    # ------------------------------------------------------------------
    # Raster/vector image resolution
    # ------------------------------------------------------------------

    # Implements: REQ-p00080-H
    def _resolve_image_paths(
        self,
        line: str,
        source_file: str,
        owning_repo_root: Path | None = None,
    ) -> str:
        """Rewrite relative image references to absolute paths.

        Pandoc runs against a temp file in ``/tmp/``, so relative image
        paths in the assembled markdown resolve to nothing and images
        silently vanish from the PDF. Each reference is resolved against
        the *source spec file's* directory in the file's *owning* repo,
        then against that repo's root -- mirroring
        ``_resolve_mermaid_images``. Anchoring per file is what keeps
        federation correct: different files resolve against different
        repo roots, which a single global ``--resource-path`` cannot
        express (and refs relative to spec subdirectories aren't on the
        resource path at all).

        URLs are left untouched. An absolute path is left untouched too,
        but is reported when it does not exist -- otherwise pandoc aborts
        with a bare filesystem error that names neither the spec file nor
        a remedy. A reference reachable only through a resource root is
        left unchanged, since pandoc's ``--resource-path`` resolves it. A
        reference reachable from nowhere is left unchanged as well (there
        is nothing better to write) but is recorded as a diagnostic,
        because an image that vanishes from the compiled document without
        a word is the silent omission REQ-p00080's REQ-p00019 instance
        prohibits.

        Every existence probe uses the percent-decoded reference, because
        that is what pandoc resolves against; probing the raw text would
        report a reference pandoc places perfectly well. The reference is
        still reported and rendered exactly as the author wrote it.
        """
        anchor = owning_repo_root if owning_repo_root is not None else self._graph.repo_root

        def _replace(match: re.Match) -> str:
            prefix = match.group(1)  # ![alt](
            img_path = match.group(2)  # relative/path.png
            suffix = match.group(3)  # optional "title" + )

            if "://" in img_path:
                return match.group(0)

            decoded = unquote(img_path)

            if Path(decoded).is_absolute():
                target = Path(decoded)
                if not target.exists():
                    self._record_diagnostic(
                        AssemblyDiagnostic(
                            kind="image",
                            reference=img_path,
                            source_file=source_file,
                            repo=self._repo_name_for_root(owning_repo_root),
                            searched=(str(target),),
                            cause=(
                                "Absolute image path does not exist; no repository can supply it."
                            ),
                            remedy=(
                                "Correct the path, or make the reference "
                                "relative to the spec file so it resolves "
                                "inside the repository."
                            ),
                        )
                    )
                return match.group(0)

            # Resolve relative to the source file's directory first
            source_dir = Path(source_file).parent
            searched: list[Path] = [(anchor / source_dir / decoded).resolve()]
            candidate = searched[0]
            if not candidate.exists():
                # Then relative to the owning repo root
                candidate = (anchor / decoded).resolve()
                searched.append(candidate)
            if not candidate.exists():
                if not self._reachable_via_resource_root(decoded):
                    self._record_unresolved_reference(
                        kind="image",
                        reference=img_path,
                        source_file=source_file,
                        owning_repo_root=owning_repo_root,
                        searched=searched,
                    )
                return match.group(0)  # Leave for --resource-path fallback

            return f"{prefix}{candidate}{suffix}"

        return _IMAGE_REF_RE.sub(_replace, line)

    def _record_unresolved_reference(
        self,
        *,
        kind: str,
        reference: str,
        source_file: str,
        owning_repo_root: Path | None,
        searched: list[Path],
    ) -> None:
        """Record a reference no repository could satisfy."""
        locations = [str(p) for p in searched]
        locations.extend(
            str(root / reference)
            for root in self.resource_roots()
            if str(root / reference) not in locations
        )
        self._record_diagnostic(
            AssemblyDiagnostic(
                kind=kind,
                reference=reference,
                source_file=source_file,
                repo=self._repo_name_for_root(owning_repo_root),
                searched=tuple(locations),
                cause="File not found in any repository of the compiled graph.",
                remedy=(
                    "Add the file, correct the reference, or remove the reference from the spec."
                ),
            )
        )

    @staticmethod
    def _generate_mermaid_png(mmd_path: Path, png_path: Path) -> Path | None:
        """Generate a PNG from a Mermaid .mmd file using mmdc.

        Returns the PNG path on success, None on failure.
        """
        mmdc = shutil.which("mmdc")
        if not mmdc:
            log.warning("mmdc not found, cannot render %s", mmd_path.name)
            return None

        try:
            subprocess.run(
                [mmdc, "-i", str(mmd_path), "-o", str(png_path), "-b", "white"],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return png_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.warning("Failed to render %s: %s", mmd_path.name, exc)
            return None

    # ------------------------------------------------------------------
    # File grouping
    # ------------------------------------------------------------------

    def _group_by_file(self) -> dict[str, list[GraphNode]]:
        """Group requirement nodes by their source file path.

        Returns:
            Dict mapping file path → list of requirement nodes (document order).
        """
        groups: dict[str, list[GraphNode]] = defaultdict(list)
        # Implements: REQ-d00129-D, REQ-d00129-E
        for node in self._graph.nodes_by_kind(NodeKind.REQUIREMENT):
            _fn = node.file_node()
            _rp = _fn.get_field("relative_path") if _fn else None
            if _rp:
                groups[_rp].append(node)

        # Sort nodes within each file by source line (document order)
        for path in groups:
            groups[path].sort(key=lambda n: n.get_field("parse_line") or 0)

        return dict(groups)

    # ------------------------------------------------------------------
    # Level partitioning
    # ------------------------------------------------------------------

    def _partition_by_level(self, file_groups: dict[str, list[GraphNode]]) -> dict[str, list[str]]:
        """Partition file paths into level buckets (PRD/OPS/DEV).

        Each file is assigned to the level of its highest-level requirement
        (min level_number).

        Returns:
            Dict mapping level name → list of file paths.
        """
        buckets: dict[str, list[str]] = defaultdict(list)
        for path, nodes in file_groups.items():
            min_level = self._min_level_for_nodes(nodes)
            if min_level:
                buckets[min_level].append(path)
        return dict(buckets)

    def _min_level_for_nodes(self, nodes: list[GraphNode]) -> str | None:
        """Return the highest-priority level name among nodes.

        Level values from the graph may be lowercase (prd/ops/dev).
        Returns the canonical uppercase key (PRD/OPS/DEV).
        """
        best_order = float("inf")
        best_level = None
        for node in nodes:
            level = node.level
            if level:
                level_upper = level.upper()
                if level_upper in self._level_order:
                    order = self._level_order[level_upper]
                    if order < best_order:
                        best_order = order
                        best_level = level_upper
        return best_level

    # ------------------------------------------------------------------
    # Graph-depth ordering
    # ------------------------------------------------------------------

    def _sort_files_by_depth(
        self,
        file_paths: list[str],
        file_groups: dict[str, list[GraphNode]],
    ) -> list[str]:
        """Sort files by the minimum graph depth of their requirements.

        Graph depth = fewest ancestor hops to a root node via BFS on iter_parents().
        Files with root requirements (depth 0) sort first.

        Returns:
            Sorted list of file paths.
        """

        def file_sort_key(path: str) -> tuple[int, str]:
            nodes = file_groups.get(path, [])
            min_depth = min(
                (self._node_depth(n) for n in nodes),
                default=999,
            )
            return (min_depth, path)

        return sorted(file_paths, key=file_sort_key)

    @staticmethod
    def _node_depth(node: GraphNode) -> int:
        """Compute the graph depth of a node via BFS on parents.

        Depth 0 = root node (no domain parents).
        FILE parents are excluded from depth calculation since they
        represent structural containment, not domain hierarchy.
        """
        from elspais.graph.GraphNode import NodeKind

        depth = 0
        visited: set[str] = {node.id}
        frontier = [node]
        while frontier:
            next_frontier: list[GraphNode] = []
            for n in frontier:
                for parent in n.iter_parents():
                    if parent.id not in visited and parent.kind != NodeKind.FILE:
                        visited.add(parent.id)
                        next_frontier.append(parent)
            if next_frontier:
                depth += 1
                frontier = next_frontier
            else:
                break
        return depth

    def _is_associated_node(self, node: GraphNode) -> bool:
        """Check if a node belongs to an associated repository.

        Detects associated-repo IDs by checking for an uppercase segment
        after the namespace prefix (e.g., REQ-CAL-p00001 has "CAL" segment).
        """
        import re

        namespace = self._resolver.config.namespace
        prefix = f"{namespace}-"
        if node.id.startswith(prefix):
            after_prefix = node.id[len(prefix) :]
            if re.match(r"^[A-Z]{2,}-[a-z]", after_prefix):
                return True
        return False

    def _filter_by_depth(
        self,
        file_paths: list[str],
        file_groups: dict[str, list[GraphNode]],
    ) -> list[str]:
        """Filter files by max depth, excluding associated-repo files from filtering.

        Associated-repo files (detected via namespace pattern) are always included.
        Core files are included only if their minimum depth < max_depth.
        """
        result: list[str] = []
        for path in file_paths:
            nodes = file_groups.get(path, [])
            if any(self._is_associated_node(n) for n in nodes):
                result.append(path)
                continue
            min_depth = min(
                (self._node_depth(n) for n in nodes),
                default=999,
            )
            if min_depth < self._max_depth:
                result.append(path)
        return result

    # ------------------------------------------------------------------
    # Topic index
    # ------------------------------------------------------------------

    def _build_topic_index(
        self,
        file_groups: dict[str, list[GraphNode]],
        file_owners: dict[str, str] | None = None,
    ) -> list[str]:
        """Build an alphabetized topic index.

        Topic sources:
        1. Filename words (strip level prefix, split on '-')
        2. File-level Topics: lines (scanned from source file)
        3. Requirement-level Topics: lines (from REMAINDER children in graph)

        When ``file_owners`` is supplied, requirement entries belonging
        to an associate repo render with a ``[<repo_name>]`` prefix so
        readers can tell where each cross-repo section originates.

        Returns:
            List of Markdown lines for the index section.
        """
        # topic → set of (req_id, req_title, repo_name)
        index: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        owners = file_owners or {}

        def _repo_for_node(node: GraphNode, fallback: str) -> str:
            try:
                return self._graph.repo_for(node.id).name
            except KeyError:
                return fallback

        for file_path, nodes in file_groups.items():
            file_owner = owners.get(file_path, "")
            # Source 1: filename words
            filename_topics = self._topics_from_filename(file_path)
            for topic in filename_topics:
                for node in nodes:
                    index[topic].add((node.id, node.get_label(), _repo_for_node(node, file_owner)))

            # Source 2: file-level Topics: lines (scan file directly)
            file_topics = self._topics_from_file(
                file_path,
                owning_repo_root=self._repo_root_for_owner(file_owner),
            )
            for topic in file_topics:
                for node in nodes:
                    index[topic].add((node.id, node.get_label(), _repo_for_node(node, file_owner)))

            # Source 3: requirement-level REMAINDER children with Topics: lines
            for node in nodes:
                req_topics = self._topics_from_requirement_remainders(node)
                for topic in req_topics:
                    index[topic].add((node.id, node.get_label(), _repo_for_node(node, file_owner)))

        if not index:
            return []

        # Render as alphabetized list
        lines: list[str] = []
        host_name = self._graph.root_repo_name
        for topic in sorted(index.keys(), key=str.lower):
            entries = sorted(index[topic], key=lambda e: e[0])
            parts: list[str] = []
            for req_id, _title, repo_name in entries:
                if repo_name and repo_name != host_name:
                    parts.append(f"[{repo_name}] [{req_id}](#{req_id})")
                else:
                    parts.append(f"[{req_id}](#{req_id})")
            refs = ", ".join(parts)
            lines.append(f"**{topic}**: {refs}")
            lines.append("")

        return lines

    def _topics_from_filename(self, file_path: str) -> list[str]:
        """Extract topics from a filename by stripping level prefix and splitting on '-'.

        Examples:
            'prd-pdf-generation.md' → ['pdf', 'generation']
            'ops-cicd.md' → ['cicd']
            '07-graph-architecture.md' → ['graph', 'architecture']
        """
        stem = Path(file_path).stem
        cleaned = self._level_prefix_re.sub("", stem)
        if not cleaned:
            return []
        words = [w for w in cleaned.split("-") if w]
        return words

    def _topics_from_file(self, file_path: str, owning_repo_root: Path | None = None) -> list[str]:
        """Extract Topics: lines from the pre-requirement section of a file."""
        resolved, searched = self._resolve_path_candidates(
            file_path, owning_repo_root=owning_repo_root
        )
        if not resolved or not resolved.exists():
            # Recorded here too because overview mode can index a file it
            # never renders. `_record_diagnostic` dedupes, so a file missed
            # by both passes is still reported once.
            self._record_unreadable_source_file(file_path, owning_repo_root, searched)
            return []
        text = resolved.read_text(encoding="utf-8")
        topics: list[str] = []
        for line in text.split("\n"):
            # Stop at first requirement heading
            if _REQ_HEADING_RE.match(line):
                break
            match = re.match(r"Topics:\s*(.+)", line, re.IGNORECASE)
            if match:
                for t in match.group(1).split(","):
                    t = t.strip()
                    if t:
                        topics.append(t)
        return topics

    @staticmethod
    def _topics_from_requirement_remainders(req_node: GraphNode) -> list[str]:
        """Extract topics from REMAINDER children of a requirement node."""
        topics: list[str] = []
        for child in req_node.iter_children():
            if child.kind == NodeKind.REMAINDER:
                text = child.get_field("text", "") or ""
                for line in text.split("\n"):
                    match = re.match(r"Topics:\s*(.+)", line, re.IGNORECASE)
                    if match:
                        for t in match.group(1).split(","):
                            t = t.strip()
                            if t:
                                topics.append(t)
        return topics
