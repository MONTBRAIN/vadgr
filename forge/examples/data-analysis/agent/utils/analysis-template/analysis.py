#!/usr/bin/env python3
"""
Analysis Script Template

This is a starter template. Copy this file to the task directory and customize
the functions below based on the approved analysis plan.

Usage:
    python analysis.py
"""

import os
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving plots
import matplotlib.pyplot as plt
import seaborn as sns


# --- Configuration ---
# Customize these values for each task

DATA_PATH = "data.csv"  # Update with the actual path to the dataset
OUTPUT_DIR = "output"


def setup():
    """Create output directory if it does not exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sns.set_theme(style="whitegrid")


def load_data(path=DATA_PATH):
    """
    Load the dataset from a CSV file.

    Customize: adjust parsing options (encoding, delimiter, date columns)
    as needed for the specific dataset.
    """
    if not os.path.exists(path):
        print(f"Error: Dataset not found: {path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(path)
    print(f"Loaded {len(df):,} rows, {len(df.columns)} columns from {path}")
    return df


def compute_metrics(df):
    """
    Compute summary statistics and derived metrics.

    Customize: replace the placeholder logic below with the specific
    metrics from the approved analysis plan.

    Returns:
        pd.DataFrame with summary statistics
    """
    # Placeholder: compute basic summary stats for all numeric columns
    summary = df.describe().T
    summary["null_count"] = df.isna().sum()
    summary["null_pct"] = (df.isna().sum() / len(df) * 100).round(2)

    # Save summary stats
    output_path = os.path.join(OUTPUT_DIR, "summary_stats.csv")
    summary.to_csv(output_path)
    print(f"Saved summary statistics to {output_path}")

    return summary


def generate_charts(df):
    """
    Generate visualization charts and save as PNG files.

    Customize: replace the placeholder charts below with the specific
    charts from the approved analysis plan. Each chart should:
    - Have a descriptive title
    - Have labeled axes with units
    - Be saved to OUTPUT_DIR as a PNG

    Follow these chart type guidelines:
    - Categorical data: bar chart (plt.bar / sns.countplot)
    - Continuous data: histogram (plt.hist / sns.histplot)
    - Time series: line chart (plt.plot / sns.lineplot)
    - Relationships: scatter plot (plt.scatter / sns.scatterplot)
    - Distributions: box plot (sns.boxplot)
    - Correlations: heatmap (sns.heatmap)
    """
    chart_num = 0

    # Placeholder chart 1: distribution of first numeric column
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        col = numeric_cols[0]
        chart_num += 1
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.histplot(df[col].dropna(), kde=True, ax=ax)
        ax.set_title(f"Distribution of {col}")
        ax.set_xlabel(col)
        ax.set_ylabel("Count")
        path = os.path.join(OUTPUT_DIR, f"chart_{chart_num}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved chart: {path}")

    # Placeholder chart 2: correlation heatmap (if multiple numeric columns)
    if len(numeric_cols) >= 2:
        chart_num += 1
        fig, ax = plt.subplots(figsize=(10, 8))
        corr_matrix = df[numeric_cols].corr()
        sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
        ax.set_title("Correlation Heatmap")
        path = os.path.join(OUTPUT_DIR, f"chart_{chart_num}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved chart: {path}")

    # Add more charts here based on the analysis plan
    # chart_num += 1
    # fig, ax = plt.subplots(figsize=(10, 6))
    # ...
    # fig.savefig(os.path.join(OUTPUT_DIR, f"chart_{chart_num}.png"), ...)
    # plt.close(fig)

    print(f"Generated {chart_num} chart(s) total")


def main():
    """Run the full analysis pipeline."""
    print("Starting analysis...")
    setup()

    df = load_data()
    print()

    print("Computing metrics...")
    summary = compute_metrics(df)
    print()

    print("Generating charts...")
    generate_charts(df)
    print()

    print("Analysis complete.")
    print(f"Outputs saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
