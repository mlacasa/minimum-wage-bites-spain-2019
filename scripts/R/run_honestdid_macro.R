#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(fixest)
  library(HonestDiD)
  library(dplyr)
  library(readr)
  library(broom)
  library(stringr)
  library(tibble)
})

parse_args <- function(args) {
  out <- list(
    input = "data/derived/Panel_Main_EventStudy.csv",
    outdir = "results/r_honestdid",
    bite = "bite_y_inc_2018",
    mbar = "0.5,1.0,1.5,2.0"
  )
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) stop("Unexpected argument: ", key)
    if (i == length(args)) stop("Missing value for argument: ", key)
    out[[substring(key, 3L)]] <- args[[i + 1L]]
    i <- i + 2L
  }
  out
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
input_path <- args$input
outdir <- args$outdir
bite_var <- args$bite
mbar_vec <- as.numeric(strsplit(args$mbar, ",", fixed = TRUE)[[1]])

dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
writeLines(capture.output(sessionInfo()), file.path(outdir, "session_info.txt"))

required_cols <- c(
  "year", "rel_year", "macro_code", "macro_label", "employees_youth",
  "weight_2018", bite_var
)

panel <- readr::read_csv(input_path, show_col_types = FALSE)
missing_cols <- setdiff(required_cols, names(panel))
if (length(missing_cols) > 0L) {
  stop("Input panel is missing required columns: ", paste(missing_cols, collapse = ", "))
}

if (!(-1L %in% panel$rel_year)) {
  stop("The omitted reference period rel_year = -1 is absent.")
}
if (!(0L %in% panel$rel_year)) {
  stop("The first post-treatment period rel_year = 0 is absent.")
}

macro_panel <- panel |>
  group_by(macro_code, macro_label, year) |>
  summarise(
    emp_youth_macro = sum(employees_youth, na.rm = TRUE),
    weight_macro = sum(weight_2018, na.rm = TRUE),
    bite = first(.data[[bite_var]]),
    rel_year = first(rel_year),
    .groups = "drop"
  ) |>
  mutate(ln_emp_youth_macro = log(emp_youth_macro))

if (any(!is.finite(macro_panel$ln_emp_youth_macro))) {
  stop("Macro panel contains non-finite log youth employment.")
}
if (any(macro_panel$weight_macro <= 0 | !is.finite(macro_panel$weight_macro))) {
  stop("Macro panel contains invalid baseline weights.")
}

macro_bite_check <- macro_panel |>
  group_by(macro_code) |>
  summarise(n_bite = n_distinct(bite), .groups = "drop")
if (any(macro_bite_check$n_bite != 1L)) {
  stop("Bite is not fixed within macroterritory across time.")
}

es_macro <- fixest::feols(
  ln_emp_youth_macro ~ i(rel_year, bite, ref = -1) | macro_code + year,
  data = macro_panel,
  weights = ~weight_macro,
  vcov = ~macro_code
)

coefs_macro <- broom::tidy(es_macro, conf.int = TRUE) |>
  filter(str_detect(term, "^rel_year::")) |>
  mutate(rel_year = as.integer(str_extract(term, "-?[0-9]+"))) |>
  arrange(rel_year)

readr::write_csv(coefs_macro, file.path(outdir, "es_macro_coefs.csv"))
saveRDS(es_macro, file.path(outdir, "event_study_macro.rds"))

dynamic_terms <- names(stats::coef(es_macro))[
  stringr::str_detect(names(stats::coef(es_macro)), "^rel_year::")
]
dynamic_rel_year <- as.integer(stringr::str_extract(dynamic_terms, "-?[0-9]+"))
dynamic_order <- order(dynamic_rel_year)
dynamic_terms <- dynamic_terms[dynamic_order]
dynamic_rel_year <- dynamic_rel_year[dynamic_order]

betahat <- stats::coef(es_macro)[dynamic_terms]
sigma <- stats::vcov(es_macro)[dynamic_terms, dynamic_terms, drop = FALSE]
sigma <- (sigma + t(sigma)) / 2

n_pre <- sum(dynamic_rel_year < 0)
n_post <- sum(dynamic_rel_year >= 0)

stopifnot(
  length(dynamic_terms) > 0L,
  !anyNA(dynamic_rel_year),
  !(-1L %in% dynamic_rel_year),
  0L %in% dynamic_rel_year,
  n_pre > 0L,
  n_post > 0L,
  all(is.finite(betahat)),
  all(is.finite(sigma)),
  identical(dim(sigma), c(length(betahat), length(betahat)))
)

honest_warnings <- character()
capture_honest_warnings <- function(expr) {
  withCallingHandlers(
    expr,
    warning = function(w) {
      honest_warnings <<- unique(c(honest_warnings, conditionMessage(w)))
      invokeRestart("muffleWarning")
    }
  )
}

run_honest_target <- function(target) {
  if (target == "first_post") {
    l_vec <- c(1, rep(0, n_post - 1L))
  } else if (target == "avg_post") {
    l_vec <- rep(1 / n_post, n_post)
  } else {
    stop("Unknown target: ", target)
  }

  original <- HonestDiD::constructOriginalCS(
    betahat, sigma, n_pre, n_post, l_vec
  ) |>
    mutate(
      lb = as.numeric(lb),
      ub = as.numeric(ub),
      Delta = as.character(Delta),
      Mbar = 0
    )

  sensitivity <- capture_honest_warnings(
    HonestDiD::createSensitivityResults_relativeMagnitudes(
      betahat = betahat,
      sigma = sigma,
      numPrePeriods = n_pre,
      numPostPeriods = n_post,
      Mbarvec = mbar_vec,
      l_vec = l_vec
    )
  )

  bind_rows(original, sensitivity) |>
    as_tibble() |>
    mutate(target = target, .before = 1)
}

honest_tbl <- bind_rows(
  run_honest_target("first_post"),
  run_honest_target("avg_post")
)

readr::write_csv(honest_tbl, file.path(outdir, "honestdid_macro_results.csv"))

if (length(honest_warnings) > 0L) {
  writeLines(honest_warnings, file.path(outdir, "honestdid_macro_warnings.txt"))
}

cat("Wrote: ", file.path(outdir, "es_macro_coefs.csv"), "\n", sep = "")
cat("Wrote: ", file.path(outdir, "honestdid_macro_results.csv"), "\n", sep = "")
cat("n_pre=", n_pre, " n_post=", n_post, " bite=", bite_var, "\n", sep = "")
