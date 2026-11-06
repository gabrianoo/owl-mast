/**
 * Bootstrap feature: owns the infrastructure schema created by the first migration and exposes the
 * schema baseline through its public API. Layout: {@code api} (public contracts), {@code
 * application} (operations), {@code port} (consumer-owned interfaces), {@code adapter.*} (framework
 * and database code).
 */
package com.aisquad.owlmast.bootstrap;
