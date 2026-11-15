/**
 * Access feature: owns identity-provider and authorization contracts (AD-3).
 *
 * <ul>
 *   <li>OM-01.02: the issuer the installation trusts and its discovery readiness ({@code
 *       adapter.identity}).
 *   <li>OM-02.01 (docs/identity.md): browser sign-in with a session held by the backend, validation
 *       of presented credentials, the principal bound to an issuer and subject ({@code domain},
 *       {@code port}, {@code adapter.persistence}), the scope bound for each authenticated request,
 *       and the session outcomes recorded through the audit owner ({@code application}, {@code
 *       adapter.web}).
 * </ul>
 *
 * <p>Not here yet: tenant and project membership, roles and permissions (OM-02.02, OM-02.04),
 * external account bindings (OM-02.03), enrollment credentials, MCP OAuth and service identities
 * (Epics 4 and 5).
 */
package com.aisquad.owlmast.access;
