"""Record every published surface, then emit the coverage tables from the record.

A recorder, not a driver: it invokes the installed `vadgr` binary and calls the
daemon's routes directly. It never imports product code and never stands in for
the CLI.
"""
import json, os, subprocess, sys, urllib.error, urllib.request

BASE = os.environ["VADGR_API_URL"]
VADGR = os.environ["VADGR_BIN"]
OUT = sys.argv[1]
record = {"http": [], "cli": [], "absent": []}


def http(method, path, body=None, label=""):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        status = e.code
    except Exception as e:
        raw, status = f"<{type(e).__name__}: {e}>", 0
    try:
        parsed = json.loads(raw)
        code = (parsed.get("error") or {}).get("code") if isinstance(parsed, dict) else None
    except Exception:
        parsed, code = raw, None
    entry = {"method": method, "path": path, "label": label, "status": status,
             "code": code, "body": raw[:400]}
    record["http"].append(entry)
    # The record keeps a truncated copy; the caller gets the whole body, because
    # parsing a body you already truncated is how a sweep reads the wrong state.
    return {**entry, "raw": raw}


def absent(method, path, minor):
    e = http(method, path, {} if method in ("POST", "PUT") else None, label="absence probe")
    record["http"].pop()
    record["absent"].append({**e, "minor": minor})
    return e


def cli(*argv):
    p = subprocess.run([VADGR, *argv], capture_output=True, text=True, timeout=180)
    record["cli"].append({
        "argv": ["vadgr", *argv],
        "exit": p.returncode,
        "stdout_produced": bool(p.stdout.strip()),
        "stderr_produced": bool(p.stderr.strip()),
        "first_line": (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else "",
    })


# --- the shipped HTTP surface
http("GET", "/api/health", label="the daemon is up")
http("GET", "/api/providers", label="the provider list")
http("GET", "/api/settings/computer-use", label="the computer-use setting")
http("GET", "/api/computer-use/status", label="the runtime's own status")
http("GET", "/api/devices", label="paired devices")
listing = http("GET", "/api/runs", label="the run list")
runs = json.loads(listing["raw"] or "[]") if listing["status"] == 200 else []
if runs:
    rid = runs[0]["id"]
    http("GET", f"/api/runs/{rid}", label="one run")
    http("POST", f"/api/runs/{rid}/cancel", label="negative: cancelling a finished run")
    http("POST", f"/api/runs/{rid}/resume", label="resume")
http("GET", "/api/runs/run-does-not-exist", label="negative: no such run")
http("POST", "/api/runs", {}, label="negative: no task")
http("POST", "/api/auth/pair", label="mint a pairing code")
http("POST", "/api/auth/claim", {"pairing_token": "XXXX-XXXX", "device_name": "probe"},
     label="negative: a code that was never minted")
http("POST", "/api/providers/gemini/catalog-refresh", label="refresh a connected catalog")
http("POST", "/api/providers/openai/catalog-refresh", label="negative: refresh a disconnected one")
http("PUT", "/api/default-model", {"provider": "gemini", "model": "not-real"},
     label="negative: a model that is not in the catalog")
http("DELETE", "/api/providers/openai/connection", label="negative: disconnect what is not connected")
http("GET", "/api/provider-auth/attempt-does-not-exist", label="negative: no such attempt")

# --- deleted or not yet built, probed to confirm they are absent
for method, path, minor in [
    ("GET", "/api/agents", "deleted at 0.4.4"),
    ("POST", "/api/agents", "deleted at 0.4.4"),
    ("GET", "/api/projects", "deleted at 0.4.4"),
    ("GET", "/api/registry", "deleted at 0.4.4"),
    ("GET", "/api/workflows", "deferred, POSSIBLE_PLANS #45"),
    ("GET", "/api/conversations", "0.6.0"),
    ("PATCH", "/api/machine", "0.7.0"),
]:
    absent(method, path, minor)

# --- the installed CLI
cli("--version")
cli("health")
cli("providers")
cli("computer-use", "status")
cli("runs", "list")
cli("runs")
if runs:
    cli("runs", "get", runs[0]["id"][:8])
    cli("runs", "cancel", runs[0]["id"][:8])
    cli("runs", "resume", runs[0]["id"][:8])
cli("runs", "get", "zzzzzzzz")
cli("provider", "status")
cli("model", "list")
cli("status")
cli("logs", "--no-follow", "-n", "2")
cli("update", "--check")
cli("run", "   ")
cli("run", "x", "--provider", "gemini")
cli("runs", "get")
cli("not-a-command")

with open(OUT, "w") as f:
    json.dump(record, f, indent=1)
print(f"recorded: {len(record['http'])} http, {len(record['absent'])} absence probes, {len(record['cli'])} cli")
