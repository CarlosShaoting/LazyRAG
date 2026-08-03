package store

import "lazymind/core/common/orm"

// Preparation is an idempotent, owner-scoped Workflow start plan. It is an
// expand-only table and does not replace any legacy Runtime table.
type Preparation = orm.WorkflowPreparation

// Event is the persistent, monotonically ordered Workflow stream record.
type Event = orm.WorkflowEvent

// Command stores a facade result. Existing plugin_transition_commands remain
// untouched because legacy binaries continue to own that compatibility table.
type Command = orm.WorkflowCommand
