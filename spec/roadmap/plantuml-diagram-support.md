# PlantUML Diagram Support

**Parent**: [requirements-format-enhancements.md](./requirements-format-enhancements.md)
**Date**: 2026-01-04
**Ticket**: CUR-514

---

## Decision

Implement PlantUML generation and potentially parsing.

## Rationale

- **Text-based**: version-controllable, diff-friendly
- **Widely supported**: renders in GitHub, IDEs, CI/CD
- **Linkable**: can annotate with requirement references
- **Infrastructure integration**: can map to/from Terraform IaC files

---

## Use Cases

1. **Generate from requirements**: `elspais diagram --format plantuml`
2. **Parse diagrams**: Extract requirement references from annotated diagrams
3. **Cross-reference**: Link diagrams to requirements, operations manuals

---

## Example Output

```plantuml
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Component.puml

title Clinical Diary Platform - Requirement Hierarchy

package "Platform (REQ-p00044)" {
  [Diary App\nREQ-p00043] as diary
  [Web App\nREQ-p01042] as web
  [Portal\nREQ-p00045] as portal
  [Database\nREQ-p00046] as db
}

package "Cross-Cutting Functions" {
  [Encryption\nREQ-p01009] as encrypt
  [Audit Trail\nREQ-p00004] as audit
}

diary --> encrypt : implements
web --> encrypt : implements
portal --> audit : implements
db --> audit : implements
@enduml
```

---

## elspais Configuration

```toml
# .elspais.toml

[diagram]
format = "plantuml"
output_dir = "docs/diagrams"
```

---

## Implementation Phase

**Phase 3** (16-24 hours):

1. Implement `elspais diagram` command
2. Generate PlantUML from requirement hierarchy
3. Include Type-based coloring/grouping
4. Optionally parse PlantUML annotations back to requirements

**Deliverables**:
- PlantUML generation
- Diagram templates
- Integration documentation

---

## References

- [PlantUML](https://plantuml.com/)
- [C4 Model with PlantUML](https://c4model.com/)
