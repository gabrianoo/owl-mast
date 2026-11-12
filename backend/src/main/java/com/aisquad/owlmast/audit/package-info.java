/**
 * Audit feature: owns the versioned audit envelope, the audit-publication intent that commits with
 * each covered successful mutation, the idempotent publisher and the audit-owned history (AD-6).
 * Features record mutations only through {@code audit.api.AuditedMutations}; the contract is
 * documented in {@code docs/durable-work-and-audit-contract.md}. E16 adds full inspection, coverage
 * reporting and retention on top of the history this module owns.
 */
package com.aisquad.owlmast.audit;
