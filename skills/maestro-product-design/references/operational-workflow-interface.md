# Operational workflow interface

## Purpose

Choose and verify the primary view for one run-oriented developer workflow so
an operator can understand chronology, dependencies, parallel branches,
decisions, evidence, and measured execution facts without turning the graph
into a report or erasing the raw audit model.

## Use when

Use only when the product surface represents a workflow run, trace, job, or
multi-agent execution and the task explicitly depends on execution
dependencies, fan-out or fan-in, chronological waves, selected lineage, or
execution provenance. Generic dashboards, card layouts, backend schedulers,
historical analytics, and editable node canvases do not trigger this Guide.

## Inputs

- the operator questions and decisions the first scan must support;
- authoritative nodes, typed raw relations, timestamps, status, attempts, and
  dependency semantics;
- measured, requested, recommended, inferred, and unavailable telemetry fields
  with source and coverage;
- representative sparse and dense fixtures, including forks, joins, retries,
  missing data, failure, long localized content, and selected detail;
- supported viewport, zoom, keyboard, pointer, and assistive-technology
  conditions;
- the current rendered interface and product tokens when they exist.

## Decision checks

1. **Start from the operator question.** Name what must be understood in the
   first scan: current result, failed or blocked work, critical path,
   delegation, parallel branches, retry, evidence, or next action. A run graph
   is a spatial index into one execution, not the complete report.
2. **Choose the spatial form from the task.** Use a dependency graph when
   topology changes the decision, a timeline when elapsed order is primary, a
   table for cross-row comparison, and list-detail or cards when identity and
   contextual drill-down dominate. Keep history and aggregate analytics in a
   separate view.
3. **Derive chronological waves from authoritative dependencies.** Place older
   waves before newer waves in the product's reading direction. For a vertical
   Korean interface, place them top to bottom and keep independent siblings in
   the same wave. Do not label potential independence as observed concurrency.
4. **Keep raw semantics lossless.** Preserve every typed relation, direction,
   source, and coverage in data and selected detail. Reduce permanent geometry
   only in a separate display projection.
5. **Treat edge folding as a tested option.** Evaluate adjacent-wave or folded
   projections and fork/join trunks on representative dense fixtures. Adopt
   them only when task testing improves readability without ambiguous
   direction, invented dependencies, hidden relations, or loss of selected
   lineage. A shared trunk must represent one connected dependency component,
   not all cards in a wave.
6. **Design collapsed cards for scanning.** Keep identity or topic, decisive
   state or short result, responsibility, and only the smallest operational
   context needed for the first scan. Avoid repeating page headings, report
   prose, or a complete inspector.
7. **Disclose detail in context.** Expand the selected card in place when the
   added height preserves the user's place. Order detail by task: outcome or
   decision, assignment and handoff, evidence and verification, expertise
   lineage, then technical provenance. Keep blocking state, consequence,
   prerequisite, owner, and recovery visible without disclosure.
8. **Compress telemetry without changing its meaning.** A compact footer may
   show a localized model short name and effort, token total, and elapsed time.
   Preserve actual/requested/recommended kind, scope, attribution, reroutes,
   and coverage in accessible context. Use field-specific localized unavailable
   labels; never convert absent data to zero.
9. **Keep page navigation natural.** Prefer document scroll for long expanded
   content. Avoid nested card or inspector scroll unless the content is a
   genuinely bounded independent region. Selection rerender must reveal the
   selected card without disorienting jumps and return focus predictably on
   collapse.
10. **Provide a linear accessible contract.** A joining DAG is not an ARIA
    tree. Use ordinary headings, regions, buttons, and lists with visible focus,
    focus distinct from selection, meaningful DOM order, explicit dependency
    text when geometry is hidden, and disclosure semantics for expansion.

## Required evidence

- a card content inventory split into scan-critical, contextual, and technical
  information;
- raw edge counts and types plus the proposed display projection;
- at least one dense fork/join fixture and one missing-telemetry fixture;
- before/after task checks for chronology, dependency tracing, decision
  location, and failure or recovery;
- rendered desktop and narrow reflow checks with realistic localized content;
- keyboard, focus, zoom, selected-card reveal, and nested-scroll observations;
- provenance checks proving requested or recommended values are not labelled
  as applied measurements.

## Reject or stop when

- dependency direction or chronology is inferred from screen position instead
  of authoritative data;
- folding cannot preserve selected lineage or makes unrelated work look joined;
- the primary task is historical comparison, aggregate cost, backend
  scheduling, or free-form graph authoring;
- a visual-only graph is the sole representation of dependencies;
- missing execution measurements would be presented as actual, zero, or
  estimated without an explicit estimate contract;
- no representative dense fixture or rendered interaction is available to
  validate a structural redesign.

## Verification

Walk the representative task from the oldest wave to the final result. Trace
every fork and join through the display and the linear alternative. Confirm
that only validated display geometry is drawn while raw typed relations remain
inspectable. Expand and collapse cards by keyboard and pointer; verify visible
focus, focus return, selected reveal, stable context, document scrolling, long
content, zoom, reflow, localization, reduced motion, and hidden-edge dependency
text. Compare measured and unavailable fixtures field by field.

Source inspection, a structurally valid SVG, or a single sparse screenshot is
not verification.

## Authority and evidence boundary

- **rule** — `w3c-wcag-reflow`, `w3c-focus-order`,
  `w3c-focus-not-obscured`, `w3c-apg-disclosure`, and
  `w3c-keyboard-interface` constrain accessible reflow, focus, controls, and
  keyboard behavior. `codex-app-server` constrains which execution values can
  be measured; it does not prescribe UI.
- **observed product examples** — `github-actions-visualization`,
  `github-actions-logs`, `airflow-ui`, and `langsmith-trace` document how
  those products separate a run graph, selected detail, logs, history, or
  trace investigation. They do not prove that their layout transfers.
- **data/layout examples** — `argo-dag` supports explicit fork/join dependency
  semantics and `elk-layered` documents a layered graph algorithm.
  `w3c-treeview` defines hierarchical tree behavior and is used only as a
  negative semantic boundary for a joining DAG.
- **derived optional pattern** — top-to-bottom waves, adjacent-rank edges,
  conditional fork/join trunks, the exact card detail order, compact telemetry
  footer, natural page scroll, and geometry-to-text fallback are project
  hypotheses. Adopt them only after representative task and dense-fixture
  checks.
- **current evidence gap** — this is the broadest source lane but the frozen
  candidate artifacts do not retain a held-out dense rendered workflow,
  before/after operator task observation, localization/reflow capture, or
  telemetry provenance audit. A second overlapping operational-workflow
  candidate must be reconciled before publication.

## Counterexamples

- A monthly cost table needs sortable comparable columns, not a run graph.
- A backend retry queue can share dependency data without becoming a Product
  Design workflow-interface task.
- A file tree can use tree semantics because it has hierarchical parent-child
  structure; a joining dependency DAG cannot inherit that contract by visual
  resemblance.
- One-to-many or many-to-one trunks are not universally clearer. Keep direct
  adjacent paths when the folded option performs worse in the representative
  task check.
