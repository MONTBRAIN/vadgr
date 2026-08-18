"""Compare three recorded passes structurally, normalising only the ids that must differ."""
import json, re, sys

def norm(record):
    text = json.dumps(record, sort_keys=True)
    # The full id and the eight character prefix the listing prints: both are
    # per-pass by definition, and they are the only ids normalised.
    text = re.sub(r"run-[0-9a-f]{32}", "run-<id>", text)
    text = re.sub(r"run-[0-9a-f]{4,8}(?![0-9a-f])", "run-<id>", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}T[0-9:.+\-]+", "<time>", text)
    text = re.sub(r"\b88\d\d\b", "<port>", text)
    text = re.sub(r'"pairing_token":"[A-Z0-9\-]+"', '"pairing_token":"<code>"', text)
    return text

paths = sys.argv[1:]
records = [json.load(open(p)) for p in paths]

print("| axis | " + " | ".join(p.split("-")[-1].split(".")[0] for p in paths) + " |")
print("|---|" + "---|" * len(paths))
print("| HTTP entries | " + " | ".join(str(len(r["http"])) for r in records) + " |")
print("| absence probes | " + " | ".join(str(len(r["absent"])) for r in records) + " |")
print("| CLI entries | " + " | ".join(str(len(r["cli"])) for r in records) + " |")

def sig(r):
    return [(e["method"], e["path"].split("/api/")[-1].split("/")[0], e["status"], e["code"]) for e in r["http"]]
same_http = all(sig(records[0]) == sig(r) for r in records[1:])
cell = "same" if same_http else "DIFFER"
print("| method, path, status and error code | " + " | ".join([cell] * len(paths)) + " |")

def csig(r):
    return [(tuple(e["argv"][:3]), e["exit"], e["stdout_produced"] or e["stderr_produced"]) for e in r["cli"]]
same_cli = all(csig(records[0]) == csig(r) for r in records[1:])
cell = "same" if same_cli else "DIFFER"
print("| argv, exit code and output produced | " + " | ".join([cell] * len(paths)) + " |")

norms = [norm(r) for r in records]
cell = "identical" if len(set(norms)) == 1 else "differs"
print("| whole record, ids normalised | " + " | ".join([cell] * len(paths)) + " |")

if len(set(norms)) != 1:
    import difflib
    for line in list(difflib.unified_diff(norms[0].split(","), norms[1].split(","), lineterm=""))[:20]:
        print("    " + line)
