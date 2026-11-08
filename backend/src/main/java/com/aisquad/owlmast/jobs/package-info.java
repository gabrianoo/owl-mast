/**
 * Jobs feature: owns durable background work (AD-6). PostgreSQL holds versioned work state,
 * tenant-scoped claims, expiring fencing-token leases, persisted retry/backoff and terminal
 * outcomes; in-process Spring scheduling only wakes the processor. Other features enqueue work and
 * register handlers exclusively through {@code jobs.api}, whose contract is documented in {@code
 * docs/durable-work-and-audit-contract.md}. Layout: {@code api} (published contract), {@code
 * domain} (policy), {@code application} (enqueue, processor, fail-closed dispatch authorization),
 * {@code port} (repository the feature needs), {@code adapter.*} (R2DBC and scheduling).
 */
package com.aisquad.owlmast.jobs;
