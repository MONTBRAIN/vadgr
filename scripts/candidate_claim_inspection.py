"""Protected, GET-only inspection around the two one-use signing claims."""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import candidate_claims as claims
from scripts.validate_package_inputs import PackageInputError

RULESET_ID = 23578357
NAMESPACES = ["refs/tags/cua-signing-claims/**", "refs/tags/signing-claims/**"]
FIELDS = {"id", "source_type", "source", "target", "enforcement", "conditions",
          "rules", "created_at", "updated_at"}


def projection(rule, *, full=False):
    claims.require(isinstance(rule, dict) and FIELDS <= set(rule), "claim ruleset fields are incomplete")
    claims.require(rule["id"] == RULESET_ID and type(rule["id"]) is int
                   and rule["source_type"] == "Repository" and rule["source"] == claims.REPOSITORY
                   and rule["target"] == "tag" and rule["enforcement"] == "active",
                   "claim ruleset identity or enforcement differs")
    claims.require(rule["conditions"] == {"ref_name": {"include": NAMESPACES, "exclude": []}}
                   or rule["conditions"] == {"ref_name": {"include": list(reversed(NAMESPACES)), "exclude": []}},
                   "claim ruleset must cover exactly both namespaces without exclusions")
    claims.require(rule["rules"] in ([{"type": "update"}, {"type": "deletion"}],
                                     [{"type": "deletion"}, {"type": "update"}]),
                   "claim update/deletion protections differ")
    if full or "bypass_actors" in rule:
        claims.require(rule.get("bypass_actors") == [], "claim bypass list is absent or permits bypass")
    result = {key: rule[key] for key in FIELDS}
    for key in ("created_at", "updated_at"):
        value = rule[key]
        claims.require(isinstance(value, str) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value),
            "claim ruleset timestamp is not an exact instant")
        try:
            # GitHub renders the same instant in the authenticated viewer's zone.
            result[key] = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        except ValueError as error:
            raise claims.Refused("claim ruleset timestamp is invalid") from error
    result["conditions"] = {"ref_name": {"include": NAMESPACES, "exclude": []}}
    result["rules"] = [{"type": "deletion"}, {"type": "update"}]
    if full:
        result["bypass_actors"] = []
    # Copy the observation: later API state cannot mutate an earlier inspection.
    return claims.parse(claims.canonical(result))


def current_policy(api, *, full=False):
    rows = claims.pages(api, "rulesets?includes_parents=true&targets=tag")
    claims.require(sum(row.get("id") == RULESET_ID for row in rows) == 1,
                   "required dual-namespace ruleset is absent or ambiguous")
    return projection(claims.get(api, f"rulesets/{RULESET_ID}"), full=full)


class InspectionAPI(claims.GitHubAPI):
    """The separate administrative credential can only reach ruleset GETs here."""

    token_name = "RULESET_INSPECT_TOKEN"

    def __init__(self):
        token = os.environ.get(self.token_name)
        ordinary = os.environ.get("GH_TOKEN")
        claims.require(bool(token) and bool(ordinary) and token != ordinary,
                       "inspection requires a distinct nonempty credential")

    def request(self, method, path, body=None, binary=False):
        suffix = path.removeprefix(claims.PREFIX)
        claims.require(method == "GET" and body is None and binary is False
                       and path.startswith(claims.PREFIX)
                       and (suffix == f"rulesets/{RULESET_ID}"
                            or re.fullmatch(r"rulesets\?includes_parents=true&targets=tag&per_page=100&page=[1-9][0-9]*", suffix)),
                       "inspection client permits only exact ruleset GET requests")
        return super().request(method, path, body, binary)


def inspect_and_claim(api, inspector, auth, qualification, helper_raw):
    from scripts.candidate import cua_shared

    claims.approve(api, auth, qualification)
    helper = cua_shared.check_bound_helper(auth, helper_raw)
    before = current_policy(inspector, full=True)
    claims.require(claims.digest(claims.canonical(projection(before))) == qualification["policy_digest"],
                   "inspected policy differs from both qualified namespaces")
    for ref in (claims.claim_ref(auth), helper["signing_claim_ref"]):
        claims.require(api.request("GET", claims.PREFIX + "git/ref/" + ref[5:])[0] == 404,
                       "signing input is already claimed; no retry")
    # Both qualifications were verified before either durable claim can be created.
    ordinary = claims.create(api, auth, qualification, approval_completed=False)
    shared = cua_shared.create_shared(api, auth, qualification, helper_raw, approval_completed=False)
    after = current_policy(inspector, full=True)
    claims.require(before == after, "claim policy changed across durable claim creation")
    claims.verify(api, auth, qualification, ordinary, approval_completed=False)
    cua_shared.verify_shared(api, auth, qualification, helper_raw, shared, approval_completed=False)
    policy_digest = claims.digest(claims.canonical(before))
    witness = {"schema": 1, "identity": claims.identity(auth),
               "authorization_sha256": claims.digest(claims.canonical(auth)),
               "namespaces": NAMESPACES, "policy": before,
               "pre_policy_sha256": policy_digest, "post_policy_sha256": policy_digest,
               "claim": ordinary, "shared_claim": shared}
    return {**ordinary, "inspection": witness}, shared


def verify_witness(api, auth, qualification, claim):
    witness = claim.get("inspection")
    claims.require(isinstance(witness, dict) and set(witness) == {
        "schema", "identity", "authorization_sha256", "namespaces", "policy",
        "pre_policy_sha256", "post_policy_sha256", "claim", "shared_claim"},
        "protected inspection witness is absent or malformed")
    claims.require(witness["schema"] == 1 and witness["identity"] == claims.identity(auth)
                   and witness["authorization_sha256"] == claims.digest(claims.canonical(auth))
                   and witness["namespaces"] == NAMESPACES
                   and witness["claim"] == {k: v for k, v in claim.items() if k != "inspection"},
                   "protected inspection witness identity differs")
    full = projection(witness["policy"], full=True)
    claims.require(witness["policy"] == full
                   and witness["pre_policy_sha256"] == witness["post_policy_sha256"]
                   == claims.digest(claims.canonical(full))
                   and projection(full) == current_policy(api), "inspected claim policy changed")
    shared = witness["shared_claim"]
    from scripts.candidate import cua_shared
    cua_shared.verify_shared_receipt(api, auth, qualification, shared)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--helper-inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        auth = claims.parse(args.authorization.read_bytes())
        claims.require(os.environ.get("GITHUB_REPOSITORY") == claims.REPOSITORY
                       and os.environ.get("GITHUB_RUN_ID") == str(auth.get("run_id"))
                       and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                       and os.environ.get("GITHUB_SHA") == auth.get("trusted_sha")
                       and os.environ.get("GITHUB_REF") == "refs/heads/master",
                       "current protected workflow context differs")
        claims.require(not args.out.exists(), "claim output already exists; no retry")
        qualification = claims.parse(args.qualification.read_bytes())
        from scripts.validate_package_inputs import read_owned
        claim, shared = inspect_and_claim(claims.GitHubAPI(), InspectionAPI(), auth, qualification,
                                        read_owned(args.helper_inputs, "pre-signing-claim.json"))
        args.out.mkdir()
        for name, value in (("claim.json", claim), ("shared-claim.json", shared)):
            with (args.out / name).open("xb") as stream:
                stream.write(claims.canonical(value) + b"\n")
        print("Both durable claims passed protected pre/post inspection. No signer was invoked.")
        return 0
    except (claims.Refused, PackageInputError, OSError, KeyError, TypeError, ValueError, IndexError):
        print("Protected claim inspection refused. No retry is permitted.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
