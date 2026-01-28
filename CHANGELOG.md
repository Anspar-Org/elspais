# Changelog

All notable changes to elspais will be documented in this file.

## [0.27.0] - 2026-01-27

### Fixed
- **trace --view**: Fixed Assoc (Associated) toggle - now uses HIDE semantic consistent with PRD/OPS/DEV badges
- **trace --view**: Fixed Core toggle - clicking now hides core (non-associated) requirements with proper styling
- **trace --report**: Implemented report presets that were previously ignored
  - `--report minimal`: ID, Title, Status only (quick overview)
  - `--report standard`: ID, Title, Level, Status, Implements (default)
  - `--report full`: All fields including Body, Assertions, Hash, Code/Test refs

- **trace --view**: Version badge now shows actual elspais version (e.g., "v0.27.0") instead of hardcoded "v1"

- **trace --view**: Replaced confusing "Files" filter with "Tests" filter
  - Shows TEST nodes in tree hierarchy (with 🧪 icon)
  - Badge displays count of test nodes instead of file count
  - Clicking badge shows test rows that validate requirements

## [0.26.0] - Previous

- Multiline block comment support for code/test references
- Various bug fixes and improvements
