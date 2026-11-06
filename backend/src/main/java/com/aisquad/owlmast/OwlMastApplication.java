package com.aisquad.owlmast;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** One modular reactive backend deployable (AD-2): API plus bounded background processing. */
@SpringBootApplication
public class OwlMastApplication {

  public static void main(String[] args) {
    SpringApplication.run(OwlMastApplication.class, args);
  }
}
