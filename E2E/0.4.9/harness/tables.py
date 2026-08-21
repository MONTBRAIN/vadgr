"""Emit the coverage tables from the recorded sweep. Never typed by hand."""
import json, sys

record = json.load(open(sys.argv[1]))
esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")[:200]

print("### Shipped\n")
print("| endpoint | what was asked | status | code | response, as returned |")
print("|---|---|---|---|---|")
for e in record["http"]:
    print(f"| `{e['method']} {e['path']}` | {e['label']} | `{e['status']}` | "
          f"{('`'+e['code']+'`') if e['code'] else '-'} | `{esc(e['body'])}` |")

print("\n### Not present - probed to confirm absent, not half-wired\n")
print("| endpoint | disposition | status | response |")
print("|---|---|---|---|")
for e in record["absent"]:
    print(f"| `{e['method']} {e['path']}` | {e['minor']} | `{e['status']}` | `{esc(e['body'])}` |")

print("\n### The CLI\n")
print("| command | exit | output produced | first line |")
print("|---|---|---|---|")
for e in record["cli"]:
    produced = []
    if e["stdout_produced"]: produced.append("stdout")
    if e["stderr_produced"]: produced.append("stderr")
    print(f"| `{' '.join(e['argv'])}` | `{e['exit']}` | {', '.join(produced) or 'none'} | "
          f"`{esc(e['first_line'])}` |")

http_ok = sum(1 for e in record["http"] if e["status"])
print(f"\n{len(record['http'])} shipped endpoint calls, {http_ok} answered; "
      f"{len(record['absent'])} absence probes; {len(record['cli'])} CLI invocations.")
