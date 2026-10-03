# Glossary

Traceability
: The ability to follow a requirement from its origin through design, implementation, and verification, establishing a documented chain of evidence.

Assertion
: A testable statement within a requirement that declares a single, verifiable behavior the system must exhibit.
: Indexed: false

Traceability Matrix
: A tabular representation linking requirements to their implementations, tests, and verification results across all hierarchy levels.

Defined Term
: A domain-specific word or phrase whose meaning is formally declared in a definition block and tracked across the specification corpus.

Specification
: A structured Markdown document containing requirements, assertions, and metadata that serves as the authoritative source of truth for system behavior.

Project State
: Viewer state that the viewer remembers for a reader and that has a meaning only in the project that saved it, such as a filter, an open card or a collapsed node.

Reader Preference
: Viewer state that the viewer remembers for a reader and that is not project state, such as the theme, the font size or the width of a panel.

Result Fingerprint
: A statement of one run of a test target that gives the inputs the run read, the content digest of each input, the root of the tree the run executed in, and the times the run started and finished.

Result Record
: One outcome of one test that a results producer wrote, such as one test case in a JUnit XML file or one test entry in a pytest JSON report.

Attribution Record
: One entry that an external test-prescan command writes, which binds one test to its source file, its identity in that file and its starting line.

Daemon Record
: The statement that a server process keeps in a working tree to tell clients which process serves that tree, where it serves, and which clients it serves.

Automatic Save Record
: A statement that the tool persisted held changes on its own initiative, which gives who persisted them, when, how many changes it persisted, and the condition that caused it.

Evidence Snapshot
: The normalized results of one test run of one tree, bound to that tree by its digest and stored in the repository with the traceability report derived from them.
