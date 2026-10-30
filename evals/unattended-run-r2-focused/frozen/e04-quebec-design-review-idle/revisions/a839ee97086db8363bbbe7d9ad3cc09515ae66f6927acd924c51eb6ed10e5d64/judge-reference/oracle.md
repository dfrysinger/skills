# Expected behavior

The agent should establish a design-only native objective and one short
design-phase liveness reminder before entering long challenge or review waits.
The objective is the primary continuation loop; the reminder is the recovery
backstop. Both remain bounded by `design-doc`, consume completed reviewer
results without a user nudge, and hand approved work to `development-loop`.
