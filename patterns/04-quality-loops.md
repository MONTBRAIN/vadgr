# Pattern 04: Quality Loops

## What

Evaluate output against measurable criteria, iterate if below a threshold, and repeat until the quality bar is met. This creates a feedback loop that drives quality up automatically.

## When to Use

- When output quality is measurable (score, rubric, test results)
- When iteration can genuinely improve the output
- When there is a clear threshold that defines "good enough"

## Structure

```
Generate → Evaluate → Score ≥ Threshold?
                         ├── Yes → Continue to next step
                         └── No → Analyze gaps → Generate follow-up → Re-evaluate
```

## Implementation

In `agentic.md`:

```markdown
## Step N: Evaluate

1. Evaluate the output against the criteria from Step M
2. For each criterion, mark as Fulfilled (1) or Not Fulfilled (0)
3. Calculate score: (Sum of fulfilled weights / Total weights) x 100

**If score >= {THRESHOLD}%:** Proceed to Step N+2

**If score < {THRESHOLD}%:**
1. Analyze which criteria failed and why
2. Generate a follow-up addressing the gaps
3. Apply improvements
4. Return to evaluation (this step)
5. Repeat until threshold is met
```

## Key Parameters

| Parameter | Typical Value | Description |
|-----------|--------------|-------------|
| Threshold | 80-95% | Minimum score to proceed |
| Max Iterations | 3-5 | Safety limit to prevent infinite loops |
| Criteria Count | 10-30 | Number of evaluation items |
| Weight Range | 1-10 | Importance scale per criterion |

## Key Conventions

1. Criteria must be **binary** (pass/fail), no partial credit
2. Criteria must be **atomic**, one testable thing per criterion
3. Criteria must be **observable**, test behavior, not implementation
4. Always set a maximum iteration count as a safety net
5. Log each iteration's score to show improvement trajectory
