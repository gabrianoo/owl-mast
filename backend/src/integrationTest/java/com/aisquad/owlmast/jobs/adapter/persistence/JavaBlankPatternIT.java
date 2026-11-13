package com.aisquad.owlmast.jobs.adapter.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.testing.OwlMastPostgres;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * Review 5884091345: discovery runs {@link R2dbcWorkRepository#JAVA_BLANK} in PostgreSQL's regular
 * expression engine, not Java's, so PostgreSQL itself must match exactly the code points {@code
 * String.isBlank} refuses: every one, not a sample. The pattern is bound as a parameter, the way
 * discovery binds it, and the answer must not depend on {@code standard_conforming_strings}.
 */
class JavaBlankPatternIT {

  private static final String MATCHING_CODE_POINTS =
      "select cp from generate_series(1, 1114111) cp"
          + " where (cp < 55296 or cp > 57343) and chr(cp) ~ ? order by cp";

  /** The class as docs/durable-work-and-audit-contract.md gives it in the operator query. */
  private static final String DOCUMENTED_OPERATOR_CLASS =
      "E'^[\\\\t\\\\n\\\\u000b\\\\f\\\\r\\\\u001c-\\\\u001f \\\\u1680"
          + "\\\\u2000-\\\\u2006\\\\u2008-\\\\u200a\\\\u2028\\\\u2029\\\\u205f\\\\u3000]*$'";

  @Test
  void postgresqlMatchesExactlyWhatStringIsBlankRefuses() throws SQLException {
    List<Integer> javaBlank = new ArrayList<>();
    for (int codePoint = 1; codePoint <= Character.MAX_CODE_POINT; codePoint++) {
      boolean surrogate =
          codePoint >= Character.MIN_SURROGATE && codePoint <= Character.MAX_SURROGATE;
      if (!surrogate && Character.toString(codePoint).isBlank()) {
        javaBlank.add(codePoint);
      }
    }

    try (PostgreSQLContainer database = OwlMastPostgres.vectorChord()) {
      database.start();
      try (Connection connection = database.createConnection("")) {
        for (String conforming : List.of("on", "off")) {
          try (Statement statement = connection.createStatement()) {
            statement.execute("set standard_conforming_strings = " + conforming);
          }
          assertThat(matchingCodePoints(connection))
              .as("standard_conforming_strings = %s", conforming)
              .isEqualTo(javaBlank);
          assertThat(emptyStringMatches(connection)).isTrue();
          assertThat(documentedQueryMatches(connection))
              .as(
                  "the operator query of the contract, standard_conforming_strings = %s",
                  conforming)
              .isEqualTo(javaBlank);
        }
      }
    }
  }

  private static List<Integer> matchingCodePoints(Connection connection) throws SQLException {
    List<Integer> matching = new ArrayList<>();
    try (PreparedStatement query = connection.prepareStatement(MATCHING_CODE_POINTS)) {
      query.setString(1, R2dbcWorkRepository.JAVA_BLANK);
      try (ResultSet rows = query.executeQuery()) {
        while (rows.next()) {
          matching.add(rows.getInt(1));
        }
      }
    }
    return matching;
  }

  private static List<Integer> documentedQueryMatches(Connection connection) throws SQLException {
    List<Integer> matching = new ArrayList<>();
    try (Statement statement = connection.createStatement();
        ResultSet rows =
            statement.executeQuery(
                "select cp from generate_series(1, 1114111) cp where (cp < 55296 or cp > 57343)"
                    + " and chr(cp) ~ "
                    + DOCUMENTED_OPERATOR_CLASS
                    + " order by cp")) {
      while (rows.next()) {
        matching.add(rows.getInt(1));
      }
    }
    return matching;
  }

  private static boolean emptyStringMatches(Connection connection) throws SQLException {
    try (PreparedStatement query = connection.prepareStatement("select '' ~ ?")) {
      query.setString(1, R2dbcWorkRepository.JAVA_BLANK);
      try (ResultSet rows = query.executeQuery()) {
        rows.next();
        return rows.getBoolean(1);
      }
    }
  }
}
