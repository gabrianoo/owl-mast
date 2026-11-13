package com.aisquad.owlmast.jobs.adapter.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/**
 * Review 5883535263: discovery sorts the ids {@code TenantId} refuses after the real tenants, so
 * its pattern must name exactly the characters {@code String.isBlank} treats as blank. This checks
 * the class in Java's engine for every code point; {@code JavaBlankPatternIT} checks it in
 * PostgreSQL's, which is the one discovery runs it in.
 */
class JavaBlankPatternTest {

  @Test
  void thePatternMatchesExactlyWhatStringIsBlankRefuses() {
    Pattern blank = Pattern.compile(R2dbcWorkRepository.JAVA_BLANK);
    List<String> disagreements = new ArrayList<>();
    for (int codePoint = 0; codePoint <= Character.MAX_CODE_POINT; codePoint++) {
      String single = Character.toString(codePoint);
      if (blank.matcher(single).matches() != single.isBlank()) {
        disagreements.add(String.format("U+%04X", codePoint));
      }
    }
    assertThat(disagreements).isEmpty();
    assertThat(blank.matcher("").matches()).isTrue();
    assertThat(blank.matcher(" \t\u001f　").matches()).isTrue();
    assertThat(blank.matcher(" a ").matches()).isFalse();
  }
}
