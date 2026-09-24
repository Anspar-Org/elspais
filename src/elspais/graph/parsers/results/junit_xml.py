"""JUnit XML parser for test results.

Extracts test results from JUnit XML and records where each test lives, so a
result can be bound to the test that produced it.

Source-file binding
-------------------
A per-``<testcase>`` ``file`` attribute names the test's real source file.
When present it becomes the result's ``source_path``, so ``match = "source"``
binds the result to the scanned test node by path, and the classname-derived
``test_id`` is dropped: a classname is a Python module path, and it can never
name a ``.spec.ts`` or any other non-Python test.

Where no ``file`` attribute is written, the classname is all there is, and it
is used to synthesize a Python ``test:...::...`` ``test_id`` for a scanned
``.py`` test node to match.

Line origin
-----------
The ``line`` attribute is a pytest extension -- standard JUnit XML carries no
line at all -- and pytest counts it from zero, at the first line of the
decorated definition. The reporter declares that origin (REQ-d00254-O) and
ingestion normalises it, so the ``line`` a result carries downstream is
counted from one, like every other line in the graph.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import unescape

from elspais.graph.parsers.results.diagnostics import DiagnosticRecorder
from elspais.utilities.test_identity import build_test_id_from_result


def _is_module_record(name: str, file_attr: str) -> bool:
    """Whether a ``<testcase>`` is pytest's record of a module as a whole.

    pytest names such a record by the module's nodeid, with its path
    separators written as dots and its ``.py`` dropped, and writes the same
    path as its ``file``. A test's own record always carries a classname.
    """
    module = file_attr.replace("\\", "/")
    if module.endswith(".py"):
        module = module[: -len(".py")]
    return bool(name) and name == module.replace("/", ".")


# Pattern to extract a named XML attribute value from a raw text line.
_ATTR_RE: dict[str, re.Pattern[str]] = {}

# Attribute values pulled from raw XML text still carry entity escapes;
# ElementTree-parsed values do not. Unescape before comparing the two.
_XML_ENTITIES = {"&quot;": '"', "&apos;": "'"}


def _attr_value(text: str, attr: str) -> str | None:
    """Extract the value of *attr* from a raw XML element string."""
    pat = _ATTR_RE.get(attr)
    if pat is None:
        pat = re.compile(rf'\b{attr}="([^"]*)"')
        _ATTR_RE[attr] = pat
    m = pat.search(text)
    return unescape(m.group(1), _XML_ENTITIES) if m else None


# Implements: REQ-d00254-F, REQ-d00294-A
def _testcase_line_index(content: str) -> dict[tuple[str, str], list[int]]:
    """Map ``(classname, name)`` to the 1-based lines of its ``<testcase`` tags.

    Works when the XML is pretty-printed so each ``<testcase`` open tag sits
    on its own line; a minified (single-line) document maps everything to
    line 1. Every occurrence of a key is kept, in document order: Playwright
    writes one ``<testcase>`` per project with the same classname and name,
    and pytest writes a second one for a teardown error, and each of those
    records is a result of its own that a reader must be pointed at.
    """
    index: dict[tuple[str, str], list[int]] = {}
    for line_no, text in enumerate(content.splitlines(), start=1):
        if "<testcase" not in text:
            continue
        cn = _attr_value(text, "classname")
        nm = _attr_value(text, "name")
        if cn is not None and nm is not None:
            index.setdefault((cn, nm), []).append(line_no)
    return index


def _record_line(
    tc_lines: dict[tuple[str, str], list[int]],
    key_counts: dict[tuple[str, str], int],
    key: tuple[str, str],
    occurrence: int,
) -> int | None:
    """The line of the *occurrence*-th ``<testcase>`` carrying *key*, or None."""
    lines = tc_lines.get(key, [])
    if len(lines) != key_counts.get(key, 0) or occurrence >= len(lines):
        return None
    return lines[occurrence]


if TYPE_CHECKING:
    from elspais.utilities.patterns import IdResolver


class JUnitXMLParser(DiagnosticRecorder):
    """Parser for JUnit XML test result files.

    Parses standard JUnit XML format used by pytest, JUnit, and other
    test frameworks.

    Matches a result to its test by recorded identity, not by reading
    requirement references out of a reported test name.
    """

    def __init__(
        self,
        resolver: IdResolver | None = None,
        base_path: Path | None = None,
    ) -> None:
        """Initialize JUnitXMLParser with optional configuration.

        Args:
            resolver: IdResolver for ID structure. If None, uses defaults.
            base_path: Base path for resolving file-specific configs.
        """
        self._resolver = resolver
        self._base_path = base_path or Path(".")

    def _get_resolver(self) -> IdResolver:
        """Get IdResolver from instance or create default.

        Returns:
            IdResolver to use for parsing.
        """
        if self._resolver is not None:
            return self._resolver

        # The shipped defaults, not a configuration written out here: a
        # hand-built one describes a repository that may not exist, and
        # this one described a shape the schema does not admit at all.
        from elspais.config import config_defaults
        from elspais.utilities.patterns import build_resolver

        return build_resolver(config_defaults())

    # Implements: REQ-d00285-G
    def parse(self, content: str, source_path: str) -> list[dict[str, Any]]:
        """Parse JUnit XML content and return test result dicts.

        Args:
            content: XML file content.
            source_path: Path to the source file.

        Returns:
            List of test result dictionaries with keys:
            - ordinal: Position of the record in this artifact
            - name: Test name
            - classname: Test class name
            - status: passed, failed, skipped, or error
            - duration: Test duration in seconds
            - message: Error/failure message (if any)
        """
        results: list[dict[str, Any]] = []
        self._start_diagnostics()

        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            # A results file that will not parse yields the same empty list as
            # a suite that ran nothing. Record which of the two happened, and
            # where, before returning the empty list.
            position = getattr(exc, "position", None)
            self._record_diagnostic(
                source_path,
                f"JUnit XML did not parse: {exc}",
                line=position[0] if position else None,
            )
            return results

        # Results-file provenance: each record points back at the artifact
        # that recorded it (`result_file` = the results file itself, distinct
        # from `source_path`, which names the TEST'S source file and is the
        # RESULT->TEST match key). `result_line` is the `<testcase>` line
        # within the results file (None when the XML is minified).
        tc_lines = _testcase_line_index(content)

        # Implements: REQ-d00294-A
        # Every suite in the document, the root included where it is one:
        # a root <testsuite> holding its own <testcase>s beside nested suites
        # is still a suite, and each record in it is a result. Each testcase
        # is read once, under the suite directly holding it.
        testsuites = list(root.iter("testsuite"))

        # Implements: REQ-d00294-A
        # The k-th <testcase> with a given (classname, name) in document order
        # sits on the k-th line recorded for that key. Where the counts differ
        # (a tag the line scan could not read) no line is named, because a
        # wrong line points a reader at another record's verdict.
        occurrence: dict[int, int] = {}
        key_counts: dict[tuple[str, str], int] = {}
        for element in root.iter("testcase"):
            key = (element.get("classname", ""), element.get("name", ""))
            occurrence[id(element)] = key_counts.get(key, 0)
            key_counts[key] = occurrence[id(element)] + 1
        if not testsuites:
            # Implements: REQ-d00285-G
            # A well-formed XML document holding no test suite was still read
            # as results. Say that it held none, rather than reporting the
            # count a suite of zero tests would produce.
            self._record_diagnostic(
                source_path,
                f"XML parsed but holds no <testsuite>: root element is <{root.tag}>",
            )

        for testsuite in testsuites:
            # Implements: REQ-d00294-C
            # The `hostname` attribute of the suite that holds the record.
            # It is carried, never read as an environment here: what it
            # means depends on the producer, and only a target that declares
            # `environment = "suite-hostname"` says it means one.
            suite_hostname = testsuite.get("hostname") or None
            for testcase in testsuite.findall("testcase"):
                name = testcase.get("name", "")
                classname = testcase.get("classname", "")
                time_str = testcase.get("time", "0")

                try:
                    duration = float(time_str)
                except ValueError:
                    # Suppressed deliberately: a duration is a measurement of
                    # the run, not a fact about traceability. An unreadable
                    # one costs the record nothing that binds it to a test,
                    # so the result is kept and the timing reads as zero.
                    duration = 0.0

                # Determine status
                status = "passed"
                message = None

                failure = testcase.find("failure")
                error = testcase.find("error")
                skipped = testcase.find("skipped")

                if failure is not None:
                    status = "failed"
                    message = failure.get("message") or failure.text
                elif error is not None:
                    status = "error"
                    message = error.get("message") or error.text
                elif skipped is not None:
                    status = "skipped"
                    message = skipped.get("message") or skipped.text

                # A per-testcase `file` attribute names the test's real source
                # file. It becomes the result's source path, so the result binds
                # to the scanned test node by path and line, and the
                # classname-derived test_id is dropped: a classname is a Python
                # module path and names nothing in a `.spec.ts` or any other
                # non-Python test file.
                file_attr = testcase.get("file")
                result_source = file_attr or source_path
                line_attr = testcase.get("line")
                try:
                    line_no = int(line_attr) if line_attr else None
                except (TypeError, ValueError):
                    line_no = None

                # Generate canonical TEST node ID using test_identity utility
                test_id = None if file_attr else build_test_id_from_result(classname, name)

                result = {
                    # Implements: REQ-d00294-A
                    # The position of this record among the records read from
                    # this artifact. Ingestion builds the result id from it.
                    # Two runs of one test in two environments write two
                    # records that agree about everything else.
                    "ordinal": len(results) + 1,
                    "name": name,
                    "classname": classname,
                    "status": status,
                    "duration": duration,
                    "message": message[:200] if message else None,
                    "source_path": result_source,
                    "test_id": test_id,
                    "line": line_no,
                    "result_file": source_path or None,
                    "result_line": _record_line(
                        tc_lines, key_counts, (classname, name), occurrence[id(testcase)]
                    ),
                    "suite_hostname": suite_hostname,
                }

                # Implements: REQ-d00254-G, REQ-d00294-E
                # pytest writes a module that failed to import, or that
                # skipped itself at load (`pytest.importorskip`,
                # `pytest.skip(allow_module_level=True)`), as one record of
                # the module's own: no classname, the module's dotted path as
                # its name, its file and no line. None of the module's tests
                # ran, so that record is the outcome of each of them -- the
                # same case as `flutter test`'s `loading <file>` record.
                if (
                    file_attr
                    and not classname
                    and line_no is None
                    and status != "passed"
                    and _is_module_record(name, file_attr)
                ):
                    result["suite_load_record"] = True

                results.append(result)

        return results

    # Implements: REQ-d00054-A
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for XML files that look like JUnit results.
        """
        name = file_path.name.lower()
        return file_path.suffix.lower() == ".xml" and (
            "junit" in name or "test" in name or "result" in name
        )


def create_parser(
    resolver: IdResolver | None = None,
    base_path: Path | None = None,
) -> JUnitXMLParser:
    """Factory function to create a JUnitXMLParser.

    Args:
        resolver: Optional IdResolver for ID structure.
        base_path: Optional base path for resolving file paths.

    Returns:
        New JUnitXMLParser instance.
    """
    return JUnitXMLParser(resolver, base_path)
