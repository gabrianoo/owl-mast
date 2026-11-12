#!/usr/bin/env bash
# Negative diagnostics for OM-01.01 AC2 (backend), the OM-01.03 contract rules and OM-01.04 T4
# (frontend): inject one violation per gate into a scratch copy and assert the gate fails with a
# message naming the offending file or rule. The frontend gates need `frontend/node_modules` (run
# `npm ci` in frontend first).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/owlmast-gates.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

failures=0

fresh_copy() {
  rm -rf "$SCRATCH/repo"
  mkdir -p "$SCRATCH/repo"
  (cd "$ROOT" && tar --exclude='./.git' --exclude='./_bmad' --exclude='./_bmad-output' \
      --exclude='./.agents' --exclude='./.claude' --exclude='./.codex' --exclude='./docs' \
      --exclude='./scripts' --exclude='./.github' --exclude='**/build' --exclude='./.gradle' \
      --exclude='./.kotlin' --exclude='./frontend' -cf - .) | tar -xf - -C "$SCRATCH/repo"
}

# DurableWorkContractTest compares the published types with the contract document, which the scratch
# copy leaves out with the rest of docs/.
with_contract_document() {
  mkdir -p "$SCRATCH/repo/docs"
  cp "$ROOT/docs/durable-work-and-audit-contract.md" "$SCRATCH/repo/docs/"
}

# expect_gate_failure <name> <pattern> <gradle task and arguments...>
expect_gate_failure() {
  local name="$1" pattern="$2" log="$SCRATCH/$1.log"
  shift 2
  local task="$*"
  if (cd "$SCRATCH/repo" && ./gradlew --console=plain "$@" >"$log" 2>&1); then
    echo "FAIL [$name]: '$task' succeeded although a violation was injected"
    failures=$((failures + 1))
    return
  fi
  if grep -qE -- "$pattern" "$log"; then
    echo "ok   [$name]: '$task' failed with diagnostic matching /$pattern/"
  else
    echo "FAIL [$name]: '$task' failed but the diagnostic did not match /$pattern/"
    sed 's/^/      /' "$log" | tail -40
    failures=$((failures + 1))
  fi
}

MAIN="backend/src/main/java/com/aisquad/owlmast"

echo "== formatting gate (Spotless + google-java-format)"
fresh_copy
sed -i 's/^public class OwlMastApplication {$/public   class    OwlMastApplication    {/' \
  "$SCRATCH/repo/$MAIN/OwlMastApplication.java"
expect_gate_failure formatting 'OwlMastApplication\.java.*(violations|violation)|spotlessApply' :backend:spotlessJavaCheck

echo "== static-analysis gate (Error Prone, -Xlint -Werror)"
fresh_copy
cat >"$SCRATCH/repo/$MAIN/bootstrap/application/DeadExceptionViolation.java" <<'JAVA'
package com.aisquad.owlmast.bootstrap.application;

final class DeadExceptionViolation {
  private DeadExceptionViolation() {}

  static void check() {
    new IllegalStateException("never thrown");
  }
}
JAVA
expect_gate_failure error-prone '\[DeadException\].*DeadExceptionViolation\.java|DeadExceptionViolation\.java.*\[DeadException\]' :backend:compileJava

echo "== lombok convention gate (flagged blanket generators)"
fresh_copy
cat >"$SCRATCH/repo/$MAIN/bootstrap/application/DataViolation.java" <<'JAVA'
package com.aisquad.owlmast.bootstrap.application;

@lombok.Data
class DataViolation {
  private String mutable;
}
JAVA
expect_gate_failure lombok 'DataViolation\.java.*@Data|Use of @Data is flagged' :backend:compileJava

echo "== module dependency gate (ArchUnit feature rules)"
fresh_copy
cat >"$SCRATCH/repo/$MAIN/platform/PlatformLeak.java" <<'JAVA'
package com.aisquad.owlmast.platform;

import com.aisquad.owlmast.bootstrap.api.SchemaBaselineQuery;

/** Deliberate violation: platform depending on a feature. */
public final class PlatformLeak {
  private final SchemaBaselineQuery query;

  public PlatformLeak(SchemaBaselineQuery query) {
    this.query = query;
  }

  public SchemaBaselineQuery query() {
    return query;
  }
}
JAVA
expect_gate_failure module-rules 'platform must not depend on feature packages|PlatformLeak' \
  :backend:test --tests com.aisquad.owlmast.architecture.FeatureModuleRulesTest

echo "== layering gate (ArchUnit: api is the lowest layer of a feature, E01-R-10)"
fresh_copy
cat >"$SCRATCH/repo/$MAIN/bootstrap/api/LayerLeak.java" <<'JAVA'
package com.aisquad.owlmast.bootstrap.api;

import com.aisquad.owlmast.bootstrap.port.SchemaBaselineRepository;

/** Deliberate violation: a published api type that exposes the feature's own port. */
public record LayerLeak(SchemaBaselineRepository repository) {}
JAVA
expect_gate_failure layering 'api must not depend on application, domain or port' \
  :backend:test --tests com.aisquad.owlmast.architecture.FeatureModuleRulesTest

echo "== tenant-internal grant gate (OM-01.03 AC7, E01-R-03: only the jobs owner grants the privilege)"
fresh_copy
with_contract_document
cat >"$SCRATCH/repo/$MAIN/audit/adapter/config/SelfGrantedWork.java" <<'JAVA'
package com.aisquad.owlmast.audit.adapter.config;

import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.application.TenantInternalGrants;
import java.util.Set;

/** Deliberate violation: a feature module granting itself tenant-internal system work. */
public final class SelfGrantedWork {
  private SelfGrantedWork() {}

  public static TenantInternalGrants grants() {
    return new TenantInternalGrants(Set.of(WorkType.of("audit.self-granted")));
  }
}
JAVA
expect_gate_failure tenant-internal-grant 'tenant-internal system work is granted only by the jobs owner' \
  :backend:test --tests com.aisquad.owlmast.architecture.DurableWorkContractTest

echo "== wake-up source gate (OM-01.03 AC9: scheduling only in jobs.adapter.scheduling)"
fresh_copy
with_contract_document
cat >"$SCRATCH/repo/$MAIN/audit/application/RogueScheduler.java" <<'JAVA'
package com.aisquad.owlmast.audit.application;

import org.springframework.scheduling.annotation.Scheduled;

/** Deliberate violation: a second wake-up source outside the jobs scheduling adapter. */
public class RogueScheduler {

  @Scheduled(fixedDelay = 1000)
  public void wake() {}
}
JAVA
expect_gate_failure wake-up-source 'scheduling annotations live only in jobs.adapter.scheduling' \
  :backend:test --tests com.aisquad.owlmast.architecture.DurableWorkContractTest

echo "== published contract gate (OM-01.03 AC9: the frozen v1 shape of jobs.api and audit.api)"
fresh_copy
with_contract_document
# A published bound changes its value: the frozen line `constant ...MAX_PAYLOAD_ENTRIES = 32` no longer holds.
sed -i 's/int MAX_PAYLOAD_ENTRIES = 32;/int MAX_PAYLOAD_ENTRIES = 33;/' "$SCRATCH/repo/$MAIN/jobs/api/WorkItemContract.java"
grep -q 'int MAX_PAYLOAD_ENTRIES = 33;' "$SCRATCH/repo/$MAIN/jobs/api/WorkItemContract.java" \
  || { echo "FAIL [contract-shape]: the violation could not be injected (WorkItemContract.MAX_PAYLOAD_ENTRIES moved)"; failures=$((failures + 1)); }
expect_gate_failure contract-shape 'every frozen v1 line must still hold' \
  :backend:test --tests com.aisquad.owlmast.architecture.DurableWorkContractTest

echo "== qualified JDK gate (exact runtime version enforced on the daemon JVM)"
fresh_copy
expect_gate_failure jdk-pin 'is not the qualified JDK.*Eclipse Adoptium 27\.0\.0\+35' \
  help -Powlmast.qualified.jdk.runtime=27.0.0+35

# ---------------------------------------------------------------------------------------------
# Frontend gates (OM-01.04-T4). The scratch copy shares the locked node_modules through a symlink
# and carries the planning assets the token/owl-mark tests read.
FRONTEND="$ROOT/frontend"
UX_REL="_bmad-output/planning-artifacts/ux-designs/ux-owl-mast-2026-11-05"
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "FAIL [frontend]: $FRONTEND/node_modules is missing; run (cd frontend && npm ci) before this script"
  exit 1
fi

fresh_frontend() {
  rm -rf "$SCRATCH/fe"
  mkdir -p "$SCRATCH/fe/frontend" "$SCRATCH/fe/$UX_REL"
  (cd "$FRONTEND" && tar --exclude='./node_modules' --exclude='./dist' --exclude='./coverage' \
      --exclude='./playwright-report' --exclude='./test-results' -cf - .) | tar -xf - -C "$SCRATCH/fe/frontend"
  ln -s "$FRONTEND/node_modules" "$SCRATCH/fe/frontend/node_modules"
  cp "$ROOT/$UX_REL/DESIGN.md" "$SCRATCH/fe/$UX_REL/DESIGN.md"
  cp -R "$ROOT/$UX_REL/assets" "$SCRATCH/fe/$UX_REL/assets"
}

# expect_frontend_failure <name> <pattern> <npm/npx command and arguments...>
expect_frontend_failure() {
  local name="$1" pattern="$2" log="$SCRATCH/$1.log"
  shift 2
  local task="$*"
  if (cd "$SCRATCH/fe/frontend" && "$@" >"$log" 2>&1); then
    echo "FAIL [$name]: '$task' succeeded although a violation was injected"
    failures=$((failures + 1))
    return
  fi
  if grep -qE -- "$pattern" "$log"; then
    echo "ok   [$name]: '$task' failed with diagnostic matching /$pattern/"
  else
    echo "FAIL [$name]: '$task' failed but the diagnostic did not match /$pattern/"
    sed 's/^/      /' "$log" | tail -40
    failures=$((failures + 1))
  fi
}

echo "== frontend accessibility lint gate (eslint-plugin-jsx-a11y strict)"
fresh_frontend
cat >"$SCRATCH/fe/frontend/src/routes/AccessibilityViolation.tsx" <<'TSX'
export function AccessibilityViolation() {
  return <img src="/owl-mark.svg" />;
}
TSX
# The rule id alone: ESLint prints the file name on its own line, so matching the file would accept
# any failure in the fixture (a parse error, an unrelated rule) even with jsx-a11y removed.
expect_frontend_failure frontend-a11y-lint 'jsx-a11y/alt-text' npm run lint

echo "== frontend type gate (tsc strict)"
fresh_frontend
cat >"$SCRATCH/fe/frontend/src/TypeViolation.ts" <<'TS'
export const count: number = 'not a number';
TS
expect_frontend_failure frontend-typecheck 'TypeViolation\.ts.*TS2322' npm run typecheck

echo "== design token gate (exact DESIGN.md palette)"
fresh_frontend
sed -i 's/--owl-primary: #2456D6;/--owl-primary: #2456D7;/' "$SCRATCH/fe/frontend/src/design/tokens.css"
expect_frontend_failure design-tokens 'owl-primary' npx vitest run src/design/tokens.test.ts

echo "== API compatibility pair gate (scripts/check-api-compatibility.py)"
cat >"$SCRATCH/incompatible-contract.properties" <<'PROPS'
apiContract.major=2
apiContract.minor=0
PROPS
if python3 "$ROOT/scripts/check-api-compatibility.py" --backend-contract "$SCRATCH/incompatible-contract.properties" >"$SCRATCH/compat.log" 2>&1; then
  echo "FAIL [api-compatibility]: check passed for an incompatible pair"
  failures=$((failures + 1))
elif grep -qE 'INCOMPATIBLE.*1\.x.*2\.0' "$SCRATCH/compat.log"; then
  echo "ok   [api-compatibility]: incompatible pair detected naming both contracts"
else
  echo "FAIL [api-compatibility]: unexpected diagnostic"; cat "$SCRATCH/compat.log"; failures=$((failures + 1))
fi

if [ "$failures" -ne 0 ]; then
  echo "$failures gate check(s) did not behave as required"
  exit 1
fi
echo "all gates fail correctly on deliberate violations"
