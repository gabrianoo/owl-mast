#!/usr/bin/env bash
# Negative diagnostics for OM-01.01 AC2 (backend) and OM-01.04 T4 (frontend): inject one violation
# per gate into a scratch copy and assert the gate fails with a message naming the offending file or
# rule. The frontend gates need `frontend/node_modules` (run `npm ci` in frontend first).
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
expect_frontend_failure frontend-a11y-lint 'AccessibilityViolation\.tsx[^\n]*|jsx-a11y/alt-text' npm run lint

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
