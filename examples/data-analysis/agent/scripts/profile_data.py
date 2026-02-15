#!/usr/bin/env python3
"""
Dataset Profiler

Reads a CSV file and outputs a structured profiling report to stdout.
Covers row/column counts, per-column statistics, type detection,
missing value analysis, and distribution summaries.

Usage:
    python profile_data.py <path_to_csv>
"""

import argparse
import sys
import os

import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(
        description="Profile a CSV dataset and output summary statistics."
    )
    parser.add_argument(
        "csv_path",
        help="Path to the CSV file to profile.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding (default: utf-8). Try 'latin-1' if utf-8 fails.",
    )
    return parser.parse_args()


def load_csv(path, encoding):
    if not os.path.exists(path):
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        df = pd.read_csv(path, encoding=encoding)
    except UnicodeDecodeError:
        print(
            f"Error: Could not decode file with encoding '{encoding}'. "
            "Try --encoding latin-1",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)
    return df


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def profile_overview(df):
    print_section("DATASET OVERVIEW")
    mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
    print(f"  Rows:           {len(df):,}")
    print(f"  Columns:        {len(df.columns)}")
    print(f"  Memory usage:   {mem_mb:.2f} MB")
    print(f"  Duplicated rows:{df.duplicated().sum():,}")


def profile_columns(df):
    print_section("COLUMN PROFILES")
    for col in df.columns:
        series = df[col]
        non_null = series.count()
        null_count = series.isna().sum()
        null_pct = (null_count / len(df)) * 100 if len(df) > 0 else 0.0
        n_unique = series.nunique()
        dtype = str(series.dtype)

        print(f"  Column: {col}")
        print(f"    dtype:        {dtype}")
        print(f"    non-null:     {non_null:,}")
        print(f"    null:         {null_count:,} ({null_pct:.1f}%)")
        print(f"    unique:       {n_unique:,}")

        # Top 5 values
        if n_unique > 0:
            top_values = series.value_counts().head(5)
            print(f"    top values:")
            for val, count in top_values.items():
                print(f"      {val!r}: {count:,}")

        # Numeric statistics
        if pd.api.types.is_numeric_dtype(series):
            desc = series.describe()
            print(f"    mean:         {desc['mean']:.4f}")
            print(f"    median:       {series.median():.4f}")
            print(f"    std:          {desc['std']:.4f}")
            print(f"    min:          {desc['min']:.4f}")
            print(f"    25%:          {desc['25%']:.4f}")
            print(f"    50%:          {desc['50%']:.4f}")
            print(f"    75%:          {desc['75%']:.4f}")
            print(f"    max:          {desc['max']:.4f}")

        # Datetime detection
        if not pd.api.types.is_numeric_dtype(series) and series.dtype == "object":
            try:
                dt_series = pd.to_datetime(series, infer_datetime_format=True)
                min_date = dt_series.min()
                max_date = dt_series.max()
                date_range = max_date - min_date
                print(f"    [detected datetime]")
                print(f"    min date:     {min_date}")
                print(f"    max date:     {max_date}")
                print(f"    date range:   {date_range}")
            except (ValueError, TypeError):
                pass

        print()


def profile_correlations(df):
    numeric_cols = df.select_dtypes(include="number").columns
    if len(numeric_cols) < 2:
        return
    print_section("NUMERIC CORRELATIONS (top pairs)")
    corr = df[numeric_cols].corr()
    pairs = []
    for i, col_a in enumerate(numeric_cols):
        for col_b in numeric_cols[i + 1 :]:
            pairs.append((col_a, col_b, corr.loc[col_a, col_b]))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    for col_a, col_b, r in pairs[:10]:
        print(f"  {col_a} <-> {col_b}: {r:.4f}")


def main():
    args = parse_args()
    df = load_csv(args.csv_path, args.encoding)

    print(f"Profiling: {args.csv_path}")

    profile_overview(df)
    profile_columns(df)
    profile_correlations(df)

    print_section("END OF PROFILE")


if __name__ == "__main__":
    main()
