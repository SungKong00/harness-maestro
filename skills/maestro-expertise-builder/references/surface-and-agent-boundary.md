# Expertise surface and handoff boundary

`$maestro-govern` owns the complete component decision and
`maestro govern classify` is its deterministic handoff. This Builder accepts
only `decision-guide` and `expertise-pack`.

Choose a Guide when an active Pack owns the same decision family, evidence
style, and evaluation method. If the trigger and procedure are also the same,
revise the existing Guide instead of adding another ID.

Choose a Pack only when all are true:

- no active Pack owns the domain;
- at least two Guides are independently selectable rather than sections of one
  checklist;
- the Pack has a shared source and evaluation policy;
- the Pack has a distinct trigger and result artifact boundary.

Also assess integration when two or more existing Packs are plausible owners.
Choose a `pack-merge` candidate only when the current top-1 Pack boundary
repeatedly drops necessary criteria or causes handoff corrections, and the
source Packs can share one trigger, result, source, evaluation, and lifecycle
boundary. Keep separate Packs when the overlap is only vocabulary or when each
Pack has an independent refresh cadence, owner, or output. A merge creates a
new Pack identity; it is not a Guide addition and it never retires the source
Packs in the producing run.

Choose `pack-extraction` instead of merge when only selected Guides from two to
four Packs share the new boundary. Require every source to contribute, preserve
the selected Guides exactly, and keep every source Pack active. If the Guide
content itself must be combined or rewritten, stop: that is semantic Guide
consolidation and needs a separate lineage and evaluation contract.

Everything else is a handoff. In particular, a cross-task rejection boundary is
a Lens candidate, execution authority is an Executor candidate, and
project-specific policy is a Convention. Return `not admitted as expertise`
with the proposed surface and builder from the classification. Persona wording
and domain knowledge alone never justify an Agent.
