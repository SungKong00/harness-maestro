# Surface and Agent boundary

Put knowledge on the narrowest surface that can enforce it:

| Need | Surface |
|---|---|
| Machine-checkable invariant | checker or schema |
| Repeated rule for one project | Convention |
| Decision criteria within an existing domain | Decision Guide |
| Reusable domain workflow with several related guides | Expertise Pack |
| Different tools, permissions, sandbox, model, approval, or isolated context | custom Agent proposal |

A custom Agent is not a richer persona. Propose one only when at least one
execution boundary is necessary and cannot be expressed by Maestro's existing
Executor routing. State the boundary, extra cost, fallback, and why a Skill or
Pack is insufficient. Never create or globally install an Agent automatically.

Check overlap before adding a surface:

- same trigger and same decision family: extend the existing guide;
- same task but different dominant decision: keep separate and add coexistence
  cases;
- project-specific constraint: use a Convention, not global expertise;
- one-off answer: keep it in the run, not the library.
