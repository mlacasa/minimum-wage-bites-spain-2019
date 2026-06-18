#!/usr/bin/env python3
"""Prepare minimum-wage bite measures for R/HonestDiD.

The script converts a reconstructed latent cell table and an outcome panel into
the long panel consumed by the R event-study and HonestDiD code.

It is intentionally generic: all project-specific column names can be supplied
through command-line arguments.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported file type: {path}")


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df.to_csv(path, index=False)
    elif suffix in {".parquet", ".pq"}:
        df.to_parquet(path, index=False)
    else:
        raise ValueError(f"Unsupported output file type: {path}")


def require_columns(df: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def normalise_key(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def add_macro_codes_if_missing(df: pd.DataFrame, macro_code_col: str, macro_label_col: str) -> pd.DataFrame:
    if macro_code_col in df.columns:
        return df
    labels = (
        df[[macro_label_col]]
        .drop_duplicates()
        .sort_values(macro_label_col)
        .reset_index(drop=True)
    )
    labels[macro_code_col] = np.arange(1, len(labels) + 1, dtype=int)
    return df.merge(labels, on=macro_label_col, how="left", validate="many_to_one")


def try_to_numeric(series: pd.Series) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    if converted.notna().all():
        return converted
    return series


def build_incidence_bite(
    latent: pd.DataFrame,
    *,
    reference_year: int,
    year_col: str,
    macro_col: str,
    sector_col: str,
    sector_name_col: str | None,
    age_col: str,
    tier_col: str,
    employees_col: str,
    youth_age: str,
    exposed_tiers: list[str],
) -> pd.DataFrame:
    require_columns(
        latent,
        [year_col, macro_col, sector_col, age_col, tier_col, employees_col],
        "latent cells",
    )

    work = latent.copy()
    work[year_col] = pd.to_numeric(work[year_col], errors="raise").astype(int)
    work[employees_col] = pd.to_numeric(work[employees_col], errors="coerce")
    work[macro_col] = normalise_key(work[macro_col])
    work[sector_col] = normalise_key(work[sector_col])
    work[age_col] = normalise_key(work[age_col])
    work[tier_col] = normalise_key(work[tier_col])

    base = work.loc[(work[year_col] == reference_year) & (work[age_col] == youth_age)].copy()
    if base.empty:
        raise ValueError(
            f"No latent-cell rows for reference_year={reference_year} and youth_age={youth_age!r}"
        )

    group_cols = [macro_col, sector_col]

    denominator = (
        base.groupby(group_cols, dropna=False)[employees_col]
        .sum()
        .rename("employees_18_25_2018")
        .reset_index()
    )

    numerator = (
        base.loc[base[tier_col].isin(exposed_tiers)]
        .groupby(group_cols, dropna=False)[employees_col]
        .sum()
        .rename("employees_18_25_exposed_2018")
        .reset_index()
    )

    bite = denominator.merge(numerator, on=group_cols, how="left", validate="one_to_one")
    bite["employees_18_25_exposed_2018"] = bite["employees_18_25_exposed_2018"].fillna(0.0)

    if (bite["employees_18_25_2018"] <= 0).any():
        bad = bite.loc[bite["employees_18_25_2018"] <= 0, group_cols].head(10)
        raise ValueError(f"Non-positive baseline youth employment in incidence bite:\n{bad}")

    bite["bite_y_inc_2018"] = (
        bite["employees_18_25_exposed_2018"] / bite["employees_18_25_2018"]
    )
    return bite


def read_cost_bite(
    path: Path | None,
    *,
    macro_col: str,
    sector_col: str,
    cost_bite_col: str,
    shortfall_col: str,
    wage_bill_col: str,
) -> pd.DataFrame | None:
    if path is None:
        return None

    cost = read_table(path)
    require_columns(cost, [macro_col, sector_col], "cost table")
    cost = cost.copy()
    cost[macro_col] = normalise_key(cost[macro_col])
    cost[sector_col] = normalise_key(cost[sector_col])

    if cost_bite_col in cost.columns:
        keep = [macro_col, sector_col, cost_bite_col]
        if shortfall_col in cost.columns:
            keep.append(shortfall_col)
        if wage_bill_col in cost.columns:
            keep.append(wage_bill_col)
        out = cost[keep].copy()
        out = out.rename(columns={cost_bite_col: "bite_y_cost_2018"})
        return out

    require_columns(cost, [shortfall_col, wage_bill_col], "cost table")
    out = cost[[macro_col, sector_col, shortfall_col, wage_bill_col]].copy()
    out[shortfall_col] = pd.to_numeric(out[shortfall_col], errors="coerce")
    out[wage_bill_col] = pd.to_numeric(out[wage_bill_col], errors="coerce")
    out["bite_y_cost_2018"] = out[shortfall_col] / out[wage_bill_col]
    return out


def build_panel(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    latent = read_table(args.latent_cells)
    outcome = read_table(args.outcome_panel)

    latent_macro_col = args.macro_col
    outcome_macro_col = args.outcome_macro_col or args.macro_col

    require_columns(
        outcome,
        [
            args.year_col,
            outcome_macro_col,
            args.sector_col,
            args.sector_name_col,
            args.outcome_employees_col,
        ],
        "outcome panel",
    )

    incidence = build_incidence_bite(
        latent,
        reference_year=args.reference_year,
        year_col=args.year_col,
        macro_col=latent_macro_col,
        sector_col=args.sector_col,
        sector_name_col=args.sector_name_col,
        age_col=args.age_col,
        tier_col=args.tier_col,
        employees_col=args.employees_col,
        youth_age=args.youth_age,
        exposed_tiers=args.exposed_tiers,
    )

    if latent_macro_col != outcome_macro_col:
        incidence = incidence.rename(columns={latent_macro_col: outcome_macro_col})

    outcome = outcome.copy()
    outcome[args.year_col] = pd.to_numeric(outcome[args.year_col], errors="raise").astype(int)
    outcome[outcome_macro_col] = normalise_key(outcome[outcome_macro_col])
    outcome[args.sector_col] = normalise_key(outcome[args.sector_col])
    outcome[args.outcome_employees_col] = pd.to_numeric(
        outcome[args.outcome_employees_col], errors="coerce"
    )

    outcome = add_macro_codes_if_missing(outcome, args.macro_code_col, outcome_macro_col)

    merge_keys = [outcome_macro_col, args.sector_col]
    panel = outcome.merge(incidence, on=merge_keys, how="left", validate="many_to_one")
    if panel["bite_y_inc_2018"].isna().any():
        bad = panel.loc[panel["bite_y_inc_2018"].isna(), merge_keys].drop_duplicates().head(10)
        raise ValueError(f"Outcome units missing incidence bite:\n{bad}")

    cost = read_cost_bite(
        args.cost_table,
        macro_col=outcome_macro_col,
        sector_col=args.sector_col,
        cost_bite_col=args.cost_bite_col,
        shortfall_col=args.shortfall_col,
        wage_bill_col=args.wage_bill_col,
    )
    if cost is not None:
        panel = panel.merge(cost, on=merge_keys, how="left", validate="many_to_one")
    else:
        panel["bite_y_cost_2018"] = np.nan

    panel = panel.rename(
        columns={
            args.year_col: "year",
            args.macro_code_col: "macro_code",
            outcome_macro_col: "macro_label",
            args.sector_col: "sector_code",
            args.sector_name_col: "sector_name",
            args.outcome_employees_col: "employees_youth",
        }
    )
    panel["sector_code"] = try_to_numeric(panel["sector_code"])
    panel["macro_code"] = try_to_numeric(panel["macro_code"])

    if "ln_employees_youth" not in panel.columns:
        if (panel["employees_youth"] <= 0).any():
            bad = panel.loc[panel["employees_youth"] <= 0, ["macro_label", "sector_code", "year"]]
            raise ValueError(f"Cannot log non-positive youth employment:\n{bad.head(10)}")
        panel["ln_employees_youth"] = np.log(panel["employees_youth"])

    baseline_weight = (
        panel.loc[panel["year"] == args.reference_year, ["macro_label", "sector_code", "employees_youth"]]
        .rename(columns={"employees_youth": "weight_2018"})
    )
    panel = panel.merge(
        baseline_weight,
        on=["macro_label", "sector_code"],
        how="left",
        validate="many_to_one",
    )

    panel["post"] = (panel["year"] >= args.treatment_year).astype(int)
    panel["first_treat"] = args.treatment_year
    panel["rel_year"] = panel["year"] - args.treatment_year
    panel["exclude_pandemic_years"] = panel["year"].isin(args.exclude_years).astype(int)

    units = (
        panel[["macro_code", "macro_label", "sector_code"]]
        .drop_duplicates()
        .sort_values(["macro_code", "sector_code", "macro_label"])
        .reset_index(drop=True)
    )
    units["unit_id"] = np.arange(1, len(units) + 1, dtype=int)
    if "unit_id" in panel.columns:
        panel = panel.drop(columns=["unit_id"])
    panel = panel.merge(units, on=["macro_code", "macro_label", "sector_code"], how="left")

    keep_cols = [
        "unit_id",
        "year",
        "rel_year",
        "macro_code",
        "macro_label",
        "sector_code",
        "sector_name",
        "employees_youth",
        "ln_employees_youth",
        "weight_2018",
        "employees_18_25_2018",
        "employees_18_25_exposed_2018",
        "bite_y_inc_2018",
        "bite_y_cost_2018",
        "post",
        "first_treat",
        "exclude_pandemic_years",
    ]
    optional_cols = [c for c in [args.shortfall_col, args.wage_bill_col] if c in panel.columns]
    panel = panel[keep_cols + optional_cols].sort_values(["unit_id", "year"]).reset_index(drop=True)

    audit = make_audit(panel, args)
    return panel, audit


def make_audit(panel: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows = []

    def add(metric: str, value: object) -> None:
        rows.append({"metric": metric, "value": value})

    add("n_rows", len(panel))
    add("n_units", panel["unit_id"].nunique())
    add("year_min", int(panel["year"].min()))
    add("year_max", int(panel["year"].max()))
    add("reference_year", args.reference_year)
    add("treatment_year", args.treatment_year)
    add("rel_year_for_reference", int(panel.loc[panel["year"] == args.reference_year, "rel_year"].iloc[0]))
    add("rel_year_for_treatment", int(panel.loc[panel["year"] == args.treatment_year, "rel_year"].iloc[0]))
    add("incidence_bite_min", panel["bite_y_inc_2018"].min())
    add("incidence_bite_max", panel["bite_y_inc_2018"].max())
    add("incidence_bite_mean", panel.drop_duplicates("unit_id")["bite_y_inc_2018"].mean())
    add("cost_bite_available", bool(panel["bite_y_cost_2018"].notna().any()))
    if panel["bite_y_cost_2018"].notna().any():
        add("cost_bite_min", panel["bite_y_cost_2018"].min())
        add("cost_bite_max", panel["bite_y_cost_2018"].max())
        add("cost_bite_mean", panel.drop_duplicates("unit_id")["bite_y_cost_2018"].mean())

    duplicated = int(panel.duplicated(["unit_id", "year"]).sum())
    add("duplicated_unit_year_rows", duplicated)

    non_positive = int((panel["employees_youth"] <= 0).sum())
    add("non_positive_employees_youth_rows", non_positive)

    bite_changes = (
        panel.groupby("unit_id")[["bite_y_inc_2018", "bite_y_cost_2018"]]
        .nunique(dropna=False)
        .max()
        .to_dict()
    )
    add("max_unique_incidence_bite_per_unit", int(bite_changes["bite_y_inc_2018"]))
    add("max_unique_cost_bite_per_unit", int(bite_changes["bite_y_cost_2018"]))

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latent-cells", type=Path, required=True)
    parser.add_argument("--outcome-panel", type=Path, required=True)
    parser.add_argument("--cost-table", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, default=None)
    parser.add_argument("--metadata-out", type=Path, default=None)

    parser.add_argument("--reference-year", type=int, default=2018)
    parser.add_argument("--treatment-year", type=int, default=2019)
    parser.add_argument("--exclude-years", type=int, nargs="*", default=[2020, 2021])

    parser.add_argument("--year-col", default="year")
    parser.add_argument("--macro-col", default="macro_label")
    parser.add_argument("--outcome-macro-col", default=None)
    parser.add_argument("--macro-code-col", default="macro_code")
    parser.add_argument("--sector-col", default="sector_code")
    parser.add_argument("--sector-name-col", default="sector_name")
    parser.add_argument("--age-col", default="age_bracket")
    parser.add_argument("--tier-col", default="salary_tier")
    parser.add_argument("--employees-col", default="employees")
    parser.add_argument("--outcome-employees-col", default="employees_youth")

    parser.add_argument("--cost-bite-col", default="BITE_Y_cost_2018")
    parser.add_argument("--shortfall-col", default="shortfall_cost_total_bin_2018")
    parser.add_argument("--wage-bill-col", default="salary_amount_total_2018")

    parser.add_argument("--youth-age", default="18_25")
    parser.add_argument("--exposed-tiers", nargs="+", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel, audit = build_panel(args)
    write_table(panel, args.out)

    audit_out = args.audit_out or args.out.with_name(args.out.stem + "_audit.csv")
    write_table(audit, audit_out)

    metadata_out = args.metadata_out or args.out.with_name(args.out.stem + "_metadata.json")
    metadata_out.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "latent_cells": str(args.latent_cells),
        "outcome_panel": str(args.outcome_panel),
        "cost_table": None if args.cost_table is None else str(args.cost_table),
        "output_panel": str(args.out),
        "audit": str(audit_out),
        "reference_year": args.reference_year,
        "treatment_year": args.treatment_year,
        "youth_age": args.youth_age,
        "exposed_tiers": args.exposed_tiers,
    }
    metadata_out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Wrote panel: {args.out} ({len(panel):,} rows)")
    print(f"Wrote audit: {audit_out}")
    print(f"Wrote metadata: {metadata_out}")


if __name__ == "__main__":
    main()
