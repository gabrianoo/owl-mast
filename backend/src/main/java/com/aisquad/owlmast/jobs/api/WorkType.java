package com.aisquad.owlmast.jobs.api;

import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Registration key of a work handler, for example {@code audit.publish}. Lower-case segments joined
 * by dots; the first segment is the owning feature.
 */
public record WorkType(String value) {

  private static final Pattern FORMAT = Pattern.compile("[a-z0-9]+(?:[.-][a-z0-9]+)*");

  public WorkType {
    Objects.requireNonNull(value, "work type");
    if (value.length() > WorkItemContract.MAX_WORK_TYPE_LENGTH
        || !FORMAT.matcher(value).matches()) {
      throw new IllegalArgumentException(
          "work type must be lower-case dotted segments of at most "
              + WorkItemContract.MAX_WORK_TYPE_LENGTH
              + " characters");
    }
  }

  public static WorkType of(String value) {
    return new WorkType(value);
  }
}
