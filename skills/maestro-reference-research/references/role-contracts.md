# Role contracts

Maestro owns routing, spawning, synthesis, and the project verdict. A
researcher is a bounded read-only evidence leaf.

## Researcher

- receives one lane, exact question, source boundary, queries, and stop
  conditions;
- opens and inspects evidence;
- returns one v2 ResearchPacket;
- reports limitations and uncertainty;
- does not see another initial lane's conclusion;
- does not spawn, synthesize the whole task, implement, publish, or promote.

## Maestro synthesizer

- validates each packet;
- merges duplicate claims without deleting meaningful disagreement;
- resolves or preserves conflicts using evidence precedence;
- creates the request-bound v2 ResearchBundle;
- returns `insufficient` when authority thresholds are unmet;
- does not let vote count substitute for proof.

## Lane admission

Start with one researcher. Add a read-only leaf only when:

1. its materials are independent;
2. its answer can change or downgrade the decision;
3. separate collection improves latency or preserves initial independence.

Use at most three initial leaves. A fourth packet is allowed only as the one
conflict follow-up with new evidence. Depth alone never creates a team.
