# Workflow contract fixtures v1

This directory is the language-neutral executable baseline for the Workflow
Agent Kit. `schemas/contract-bundle.schema.json` validates both tool envelopes
and golden scenarios. `golden/` freezes the observable projection, attempts,
artifact revisions, and durable event order for the legacy Runtime.

The fixtures intentionally use Workflow domain names. Physical `plugin_*`
database names are outside this public contract and remain confined to the
persistence compatibility boundary.

