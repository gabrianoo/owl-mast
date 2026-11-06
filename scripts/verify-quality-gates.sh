#!/usr/bin/env bash
# Negative diagnostics for OM-01.01 AC2: inject one violation per gate into a scratch copy of the
# build and assert the gate fails with a message naming the offending file or rule.
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
      --exclude='./.kotlin' -cf - .) | tar -xf - -C "$SCRATCH/repo"
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

if [ "$failures" -ne 0 ]; then
  echo "$failures gate check(s) did not behave as required"
  exit 1
fi
echo "all gates fail correctly on deliberate violations"
