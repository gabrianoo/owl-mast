/**
 * Compatibility feature (OM-01.04, AD-14): publishes the API contract version this backend
 * implements so an independently deployed frontend and the pre-rollout check can detect an
 * incompatible pair. Layout: {@code api} (descriptor records and query), {@code application}
 * (operation), {@code adapter.config} (contract/version sources), {@code adapter.web} (endpoint).
 */
package com.aisquad.owlmast.compatibility;
