---
description: Run profiling script and present summary stats (Step 2).
argument-hint: [dataset-path]
---

Read `agentic.md` for context.
Read `agent/Prompts/01_Data_Profiler.md` for profiling interpretation guidance.

Execute **Step 2: Profile Data** for dataset "$ARGUMENTS".
Run `agent/scripts/profile_data.py` against the dataset, interpret the results,
and present the profiling summary for approval before saving.
