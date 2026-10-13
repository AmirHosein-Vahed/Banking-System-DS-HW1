# AGENTS.md

## Repository state
- Only file present is `DS-Assignment1-Banking-System.pdf` (assignment brief). No implementation code yet; there are no entrypoints, tests, or build commands.

## Assignment essentials
- Distributed Systems, Assignment 1: simulated client-server banking system.
- Required ops: balance inquiry, deposit, withdraw. Optional but in-spec ACID demo: transfer.
- Constraints verified from brief:
  - Client and server must run on separate VMs; `localhost` is not acceptable.
  - Max simultaneous clients must be configurable (not hard-coded).
  - Balances must persist across server restart/crash (disk, not memory only).
  - Concurrency on same account must be serializable (no lost updates, dirty reads, negatives).
- Error cases that must be handled: unknown account, insufficient funds, negative/zero/non-numeric amount, unsupported action, missing fields, malformed JSON/random bytes.
- Logging required: request ID, client IP, action, account ID, timestamp, result, latency.
- Optional bonuses (extra credit): fault-tolerant primary/backup cluster (+10%); network-partition split-brain handling (+15%).

## Conventions for future code
- Until code exists, confirm stack and bonus scope with the user before scaffolding, since none is implied by repo files.
```