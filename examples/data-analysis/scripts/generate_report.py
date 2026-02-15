#!/usr/bin/env python3
"""
Report Generator

Takes a task folder path and compiles analysis outputs into a structured
markdown report. Reads the analysis plan, CSV summaries, and chart images
to produce a complete report.md.

Usage:
    python generate_report.py <task_folder_path>
"""

import argparse
import os
import sys
import glob


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a markdown report from analysis outputs."
    )
    parser.add_argument(
        "task_folder",
        help="Path to the task folder (e.g., tasks/2026-01-15/sales-analysis).",
    )
    return parser.parse_args()


def read_file(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def find_csvs(output_dir):
    pattern = os.path.join(output_dir, "*.csv")
    return sorted(glob.glob(pattern))


def find_charts(output_dir):
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.svg"]
    charts = []
    for pat in patterns:
        charts.extend(glob.glob(os.path.join(output_dir, pat)))
    return sorted(charts)


def csv_to_markdown_table(csv_path):
    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        if df.empty:
            return f"*Empty table: {os.path.basename(csv_path)}*"
        lines = []
        headers = list(df.columns)
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for _, row in df.head(20).iterrows():
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
        if len(df) > 20:
            lines.append(f"\n*Showing first 20 of {len(df)} rows.*")
        return "\n".join(lines)
    except Exception as e:
        return f"*Error reading {os.path.basename(csv_path)}: {e}*"


def generate_report(task_folder):
    output_dir = os.path.join(task_folder, "output")
    report_path = os.path.join(task_folder, "report.md")

    # Read supporting files
    dataset_info = read_file(os.path.join(task_folder, "01_dataset_info.md"))
    profile = read_file(os.path.join(task_folder, "02_profile.md"))
    analysis_plan = read_file(os.path.join(task_folder, "03_analysis_plan.md"))

    # Find outputs
    csvs = find_csvs(output_dir) if os.path.isdir(output_dir) else []
    charts = find_charts(output_dir) if os.path.isdir(output_dir) else []

    # Build report
    sections = []

    sections.append("# Analysis Report\n")
    sections.append("## Executive Summary\n")
    sections.append("<!-- Write a 3-5 sentence summary of key findings here -->\n")

    sections.append("## Methodology\n")
    if dataset_info:
        sections.append("### Dataset\n")
        sections.append(dataset_info + "\n")
    if profile:
        sections.append("### Profiling Summary\n")
        sections.append(profile + "\n")

    sections.append("## Findings\n")
    if analysis_plan:
        sections.append("### Analysis Plan Reference\n")
        sections.append(analysis_plan + "\n")

    # Embed data tables
    if csvs:
        sections.append("### Data Tables\n")
        for csv_path in csvs:
            name = os.path.splitext(os.path.basename(csv_path))[0]
            table = csv_to_markdown_table(csv_path)
            sections.append(f"#### {name}\n")
            sections.append(table + "\n")

    # Embed charts
    if charts:
        sections.append("### Charts\n")
        for chart_path in charts:
            name = os.path.splitext(os.path.basename(chart_path))[0]
            rel_path = os.path.relpath(chart_path, task_folder)
            sections.append(f"![{name}]({rel_path})\n")
            sections.append(f"*Figure: {name}*\n")

    sections.append("## Conclusions\n")
    sections.append("<!-- Synthesize findings and answer the original questions -->\n")

    sections.append("## Limitations\n")
    sections.append("<!-- Note data quality issues, sample size, and assumptions -->\n")

    report_content = "\n".join(sections)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"Report generated: {report_path}")
    print(f"  Data tables included: {len(csvs)}")
    print(f"  Charts embedded: {len(charts)}")


def main():
    args = parse_args()
    if not os.path.isdir(args.task_folder):
        print(f"Error: Task folder not found: {args.task_folder}", file=sys.stderr)
        sys.exit(1)
    generate_report(args.task_folder)


if __name__ == "__main__":
    main()
