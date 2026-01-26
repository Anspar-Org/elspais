"""
elspais.testing.scanner - Test file scanner for requirement references.

Scans test files for requirement ID references (e.g., REQ-d00001, REQ-p00001-A)
in function names, docstrings, and comments.

Supports configurable reference keyword (default: "Validates") and dynamic
pattern generation from PatternConfig.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from elspais.graph import GraphNode
    from elspais.utilities.patterns import PatternConfig


@dataclass
class TestReference:
    """
    A reference from a test to a requirement.

    Attributes:
        requirement_id: Normalized requirement ID (e.g., "REQ-p00001")
        assertion_label: Assertion label if present (e.g., "A" for REQ-p00001-A)
        test_file: Path to the test file
        test_name: Name of the test function/method if extractable
        line_number: Line number where reference was found
        expected_broken: True if this ref is expected to be broken (from marker)
    """

    requirement_id: str
    assertion_label: Optional[str]
    test_file: Path
    test_name: Optional[str] = None
    line_number: int = 0
    expected_broken: bool = False


@dataclass
class TestScanResult:
    """
    Result of scanning test files for requirement references.

    Attributes:
        references: Mapping of requirement IDs to their test references
        files_scanned: Number of test files scanned
        errors: List of errors encountered during scanning
        suppressed_count: Count of refs marked as expected_broken (for logging)
    """

    references: Dict[str, List[TestReference]] = field(default_factory=dict)
    files_scanned: int = 0
    errors: List[str] = field(default_factory=list)
    suppressed_count: int = 0

    def add_reference(self, ref: TestReference) -> None:
        """Add a test reference, rolling up assertion-level refs to parent."""
        # Roll up assertion-level references to the parent requirement
        req_id = ref.requirement_id
        if req_id not in self.references:
            self.references[req_id] = []
        self.references[req_id].append(ref)


def build_validates_patterns(
    pattern_config: "PatternConfig",
    keyword: str = "Validates",
) -> List[str]:
    """
    Build regex patterns for test references using PatternConfig.

    Generates patterns that match the configured requirement ID format
    with the specified reference keyword (e.g., "Validates:").

    Args:
        pattern_config: Configuration for requirement ID patterns.
        keyword: Reference keyword to match (default: "Validates").

    Returns:
        List of regex pattern strings.
    """
    # Get type IDs from config
    type_ids = pattern_config.get_all_type_ids()
    type_pattern = "|".join(re.escape(t) for t in type_ids if t)

    # Build ID pattern based on format
    id_format = pattern_config.id_format
    style = id_format.get("style", "numeric")

    if style == "numeric":
        digits = int(id_format.get("digits", 5))
        leading_zeros = id_format.get("leading_zeros", True)
        if digits > 0 and leading_zeros:
            id_pattern = f"\\d{{{digits}}}"
        elif digits > 0:
            id_pattern = f"\\d{{1,{digits}}}"
        else:
            id_pattern = "\\d+"
    elif style == "named":
        pattern_str = id_format.get("pattern", "[A-Za-z][A-Za-z0-9]+")
        id_pattern = pattern_str
    elif style == "alphanumeric":
        pattern_str = id_format.get("pattern", "[A-Z0-9]+")
        id_pattern = pattern_str
    else:
        id_pattern = "[A-Za-z0-9]+"

    # Build assertion pattern
    assertion_pattern = pattern_config.get_assertion_label_pattern()

    # Build the prefix pattern
    prefix = re.escape(pattern_config.prefix)

    # Build full requirement ID pattern
    if type_pattern:
        req_id_pattern = f"{prefix}-({type_pattern})({id_pattern})"
    else:
        req_id_pattern = f"{prefix}-({id_pattern})"

    # Create keyword patterns (case insensitive matching)
    keyword_variants = f"(?:{keyword}|{keyword.upper()}|{keyword.lower()})"

    patterns = []

    # Pattern for keyword: REQ-p00001 or REQ-p00001-A
    if type_pattern:
        # Full pattern with type code
        patterns.append(
            f"{keyword_variants}[:\\s]+{prefix}-({type_pattern}{id_pattern})(?:-({assertion_pattern}))?"
        )
    else:
        # Pattern without type code
        patterns.append(
            f"{keyword_variants}[:\\s]+{prefix}-({id_pattern})(?:-({assertion_pattern}))?"
        )

    return patterns


class TestScanner:
    """
    Scans test files for requirement ID references.

    Uses configurable patterns to find requirement references in:
    - Test function/method names
    - Docstrings
    - Comments (Validates: or IMPLEMENTS: patterns)
    """

    # Default patterns if none configured (HHT-style)
    DEFAULT_PATTERNS = [
        # Test function names: test_REQ_p00001_something or test_p00001_something
        r"test_.*(?:REQ[-_])?([pod]\d{5})(?:[-_]([A-Z]))?",
        # IMPLEMENTS comments: IMPLEMENTS: REQ-p00001 or IMPLEMENTS: REQ-p00001-A
        r"(?:IMPLEMENTS|Implements|implements)[:\s]+(?:REQ[-_])?([pod]\d{5})(?:-([A-Z]))?",
        # Direct references: REQ-p00001 or REQ-p00001-A
        r"\bREQ[-_]([pod]\d{5})(?:-([A-Z]))?\b",
    ]

    def __init__(
        self,
        reference_patterns: Optional[List[str]] = None,
        reference_keyword: str = "Validates",
    ) -> None:
        """
        Initialize the scanner with reference patterns.

        Args:
            reference_patterns: Regex patterns for extracting requirement IDs.
                               Each pattern should have groups for (type+id) and
                               optionally (assertion_label).
            reference_keyword: Keyword for test references (default: "Validates").
                              Used to build default patterns when reference_patterns
                              is not provided.
        """
        self._reference_keyword = reference_keyword

        if reference_patterns:
            patterns = reference_patterns
        else:
            # Build patterns including the keyword variant
            patterns = self._build_default_patterns(reference_keyword)

        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

    def _build_default_patterns(self, keyword: str) -> List[str]:
        """Build default patterns with the given keyword."""
        keyword_variants = f"(?:{keyword}|{keyword.upper()}|{keyword.lower()})"

        return [
            # Test function names: test_REQ_p00001_something or test_p00001_something
            r"test_.*(?:REQ[-_])?([pod]\d{5})(?:[-_]([A-Z]))?",
            # Keyword comments: Validates: REQ-p00001 or Validates: REQ-p00001-A
            f"{keyword_variants}[:\\s]+REQ[-_]?([pod]\\d{{5}})(?:-([A-Z]))?",
            # Also support IMPLEMENTS for backward compatibility
            r"(?:IMPLEMENTS|Implements|implements)[:\s]+REQ[-_]?([pod]\d{5})(?:-([A-Z]))?",
            # Direct references: REQ-p00001 or REQ-p00001-A
            r"\bREQ[-_]([pod]\d{5})(?:-([A-Z]))?\b",
        ]

    def scan_directories(
        self,
        base_path: Path,
        test_dirs: List[str],
        file_patterns: List[str],
        ignore: Optional[List[str]] = None,
    ) -> TestScanResult:
        """
        Scan test directories for requirement references.

        Detects `elspais: expected-broken-links N` markers in file headers
        (supports multiple comment styles) and marks the next N references
        as expected_broken.

        Args:
            base_path: Project root path
            test_dirs: Glob patterns for test directories (e.g., ["apps/**/test"])
            file_patterns: File patterns to match (e.g., ["*_test.py"])
            ignore: Directory names to ignore (e.g., ["node_modules"])

        Returns:
            TestScanResult with all found references and suppressed_count
        """
        result = TestScanResult()
        ignore_set = set(ignore or [])
        seen_files: Set[Path] = set()

        for dir_pattern in test_dirs:
            # Handle special cases for directory patterns
            if dir_pattern in (".", ""):
                # Current directory
                dirs_to_scan = [base_path]
            else:
                # Resolve the directory pattern
                dirs_to_scan = list(base_path.glob(dir_pattern))

            for test_dir in dirs_to_scan:
                if not test_dir.is_dir():
                    continue
                if any(ig in test_dir.parts for ig in ignore_set):
                    continue

                # Find test files in this directory
                for file_pattern in file_patterns:
                    for test_file in test_dir.glob(file_pattern):
                        if test_file in seen_files:
                            continue
                        if not test_file.is_file():
                            continue
                        seen_files.add(test_file)

                        # Scan the file (handles marker detection internally)
                        file_refs, suppressed = self._scan_file_with_marker(test_file)
                        for ref in file_refs:
                            result.add_reference(ref)
                        result.suppressed_count += suppressed
                        result.files_scanned += 1

        return result

    # Marker pattern for expected broken links - multi-language support
    # Matches various comment styles:
    # - # elspais: expected-broken-links N  (Python, Shell, Ruby, YAML)
    # - // elspais: expected-broken-links N (JS, TS, Java, C, C++, Go, Rust)
    # - -- elspais: expected-broken-links N (SQL, Lua, Ada)
    # - /* elspais: expected-broken-links N */ (CSS, C-style block comment)
    # - <!-- elspais: expected-broken-links N --> (HTML, XML)
    _EXPECTED_BROKEN_LINKS_PATTERN = re.compile(
        r"(?:"
        r"#|"           # Python, Shell, Ruby, YAML
        r"//|"          # JS, TS, Java, C, C++, Go, Rust
        r"--|"          # SQL, Lua, Ada
        r"/\*|"         # CSS, C-style block comment start
        r"<!--"         # HTML, XML comment start
        r")\s*elspais:\s*expected-broken-links\s+(\d+)",
        re.IGNORECASE
    )

    # Number of header lines to scan for marker
    _MARKER_HEADER_LINES = 20

    def _scan_file(self, file_path: Path) -> List[TestReference]:
        """
        Scan a single test file for requirement references.

        Args:
            file_path: Path to the test file

        Returns:
            List of TestReference objects found in the file
        """
        refs, _ = self._scan_file_with_marker(file_path)
        return refs

    def _scan_file_with_marker(
        self, file_path: Path
    ) -> tuple[List[TestReference], int]:
        """
        Scan a single test file for requirement references with marker support.

        Detects the expected-broken-links marker in the file header and marks
        the next N references as expected_broken.

        Args:
            file_path: Path to the test file

        Returns:
            Tuple of (list of TestReference objects, count of suppressed refs)
        """
        references: List[TestReference] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return references, 0

        lines = content.split("\n")
        current_test_name: Optional[str] = None

        # Detect marker in header and get initial suppress count
        suppress_remaining = self._detect_expected_broken_links_marker(file_path) or 0
        suppressed_count = 0

        for line_num, line in enumerate(lines, start=1):
            # Track current test function name
            test_match = re.match(r"\s*def\s+(test_\w+)", line)
            if test_match:
                current_test_name = test_match.group(1)

            # Look for requirement references
            for pattern in self._patterns:
                for match in pattern.finditer(line):
                    groups = match.groups()
                    if not groups or not groups[0]:
                        continue

                    # Extract requirement ID parts
                    type_id = groups[0]  # e.g., "p00001"
                    assertion_label = groups[1] if len(groups) > 1 else None

                    # Normalize to full requirement ID
                    if type_id.startswith("REQ-") or type_id.startswith("REQ_"):
                        req_id = type_id.replace("_", "-")
                    else:
                        req_id = f"REQ-{type_id}"

                    # Check if we have suppress budget
                    expected_broken = False
                    if suppress_remaining > 0:
                        expected_broken = True
                        suppress_remaining -= 1
                        suppressed_count += 1

                    ref = TestReference(
                        requirement_id=req_id,
                        assertion_label=assertion_label,
                        test_file=file_path,
                        test_name=current_test_name,
                        line_number=line_num,
                        expected_broken=expected_broken,
                    )
                    references.append(ref)

        return references, suppressed_count

    def _detect_expected_broken_links_marker(self, file_path: Path) -> Optional[int]:
        """
        Detect expected-broken-links marker in file header.

        Scans the first 20 lines of a file for the marker:
        # elspais: expected-broken-links N

        Args:
            file_path: Path to the file to scan

        Returns:
            The expected count N if marker is found, None otherwise
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        lines = content.split("\n")
        # Only scan header area (first N lines)
        for line in lines[: self._MARKER_HEADER_LINES]:
            match = self._EXPECTED_BROKEN_LINKS_PATTERN.search(line)
            if match:
                return int(match.group(1))

        return None

    def scan_file(self, file_path: Path) -> List[TestReference]:
        """
        Public method to scan a single file.

        Args:
            file_path: Path to the test file

        Returns:
            List of TestReference objects
        """
        return self._scan_file(file_path)


def create_test_nodes(
    scan_result: TestScanResult,
    repo_root: Path,
) -> List["GraphNode"]:
    """
    Convert TestScanResult to GraphNode objects for graph building.

    Creates a GraphNode for each unique test function that references requirements.
    The _validates_targets metric contains the list of requirement/assertion IDs
    that the test validates. The _expected_broken_targets metric contains targets
    that were marked as expected to be broken via the expected-broken-links marker.

    Args:
        scan_result: Result from TestScanner.scan_directories()
        repo_root: Repository root for relative path calculation

    Returns:
        List of GraphNode objects with kind=TEST
    """
    # NOTE: test_ref data is stored in content dict
    from elspais.graph import NodeKind, SourceLocation, GraphNode

    # Group references by (file, test_name) to create one node per test
    tests_by_key: Dict[tuple, List[TestReference]] = {}

    for req_id, refs in scan_result.references.items():
        for ref in refs:
            key = (str(ref.test_file), ref.test_name)
            if key not in tests_by_key:
                tests_by_key[key] = []
            tests_by_key[key].append(ref)

    nodes: List[GraphNode] = []

    for (file_path_str, test_name), refs in tests_by_key.items():
        file_path = Path(file_path_str)

        # Calculate relative path
        try:
            rel_path = str(file_path.relative_to(repo_root))
        except ValueError:
            rel_path = str(file_path)

        # Collect all targets this test validates and expected broken targets
        validates_targets: List[str] = []
        expected_broken_targets: List[str] = []
        for ref in refs:
            # Build target ID
            if ref.assertion_label:
                target = f"{ref.requirement_id}-{ref.assertion_label}"
            else:
                target = ref.requirement_id
            if target not in validates_targets:
                validates_targets.append(target)
            # Track expected broken targets separately
            if ref.expected_broken and target not in expected_broken_targets:
                expected_broken_targets.append(target)

        # Use first ref for line number
        first_ref = refs[0]
        line_num = first_ref.line_number

        # Create node ID
        node_id = f"TEST:{rel_path}:{test_name or 'unknown'}"

        # Create label
        label = test_name or file_path.name

        # Store test_ref data in content dict
        node = GraphNode(
            id=node_id,
            kind=NodeKind.TEST,
            label=label,
            source=SourceLocation(
                path=rel_path,
                line=line_num,
            ),
            content={
                "test_ref": {
                    "file_path": rel_path,
                    "line": line_num,
                    "test_name": test_name or "unknown",
                },
            },
            metrics={
                "_validates_targets": validates_targets,
                "_expected_broken_targets": expected_broken_targets,
                "_test_status": "unknown",  # Will be updated from test results
            },
        )

        nodes.append(node)

    return nodes
