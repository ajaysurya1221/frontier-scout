## Static safety analysis — io.modelcontextprotocol/filesystem

_Static analysis only — no server was started or executed._

**Verdict:** review · fit medium · risk medium · source trust medium · confidence medium
> REVIEW - high-risk capability; behavioral evidence recommended before adoption.

Description: Local filesystem access: read, write, and list files in a directory.

### Capability map
- `read`: likely
- `write`: likely

Dangerous flags: write

### Policy findings
- [high] capability.write: Tool exposes write capability; behavioral evidence is recommended before adoption.

