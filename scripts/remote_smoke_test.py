from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

APP_URL = os.environ.get(
    "APP_URL",
    "https://mira-agent-phase-2.orangestone-b32613df.spaincentral.azurecontainerapps.io",
)
ROOT = Path(__file__).resolve().parents[1]
DEMO_ENV = ROOT / ".demo.env"
EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ROOT / "evidence"))
EXPECTED_NODES = [
    "brief",
    "research",
    "audience",
    "performance",
    "synthesize",
    "strategy",
    "critic",
]


def main() -> None:
    analyst_jwt = os.environ.get("ANALYST_JWT") or _read_demo_jwt()
    if not analyst_jwt:
        raise RuntimeError("ANALYST_JWT is missing from environment and .demo.env")

    headers = {"Authorization": f"Bearer {analyst_jwt}"}

    print("Pinging health check...")
    health_resp = httpx.get(f"{APP_URL}/health", timeout=30.0)
    print(f"Health Response: {health_resp.status_code} - {health_resp.text}")
    assert health_resp.status_code == 200

    print("\nRunning media plan analysis...")
    crm_path = ROOT / "samples" / "crm-demo.csv"
    ga4_path = ROOT / "samples" / "ga4-demo.csv"
    data = {
        "org_id": "11111111-1111-4111-8111-111111111111",
        "brief": (
            "Product: MIRA\n"
            "Audience: B2B marketers\n"
            "Channels: google, linkedin, meta, tiktok\n"
            "Budget: 10000\n"
            "Goal: grow pipeline"
        ),
    }
    with crm_path.open("rb") as crm_file, ga4_path.open("rb") as ga4_file:
        files = {
            "crm_csv": ("crm-demo.csv", crm_file, "text/csv"),
            "ga4_csv": ("ga4-demo.csv", ga4_file, "text/csv"),
        }
        resp = httpx.post(
            f"{APP_URL}/api/media-plan",
            data=data,
            files=files,
            headers=headers,
            timeout=180.0,
        )
    print(f"Media Plan Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        resp.raise_for_status()

    body = resp.json()
    run_id = body["run_id"]
    document_markdown = body["document_markdown"]
    print(f"Run ID: {run_id}")
    print(f"Markdown preview (first 200 chars):\n{document_markdown[:200]}\n...")

    print("\nFetching audit trace logs...")
    audit_resp = httpx.get(f"{APP_URL}/api/runs/{run_id}/audit", headers=headers, timeout=30.0)
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()

    rows = audit_data.get("rows", [])
    print(f"Audit steps count: {len(rows)}")
    for row in sorted(rows, key=lambda item: item["step_index"]):
        print(f"Step {row['step_index']}: {row['node']} (Model: {row.get('model_used')})")

    nodes = [row["node"] for row in sorted(rows, key=lambda item: item["step_index"])]
    assert nodes == EXPECTED_NODES, f"Expected {EXPECTED_NODES}, but got {nodes}"

    _write_evidence(body=body, audit_data=audit_data, nodes=nodes)
    print("\nSUCCESS: 7-step graph including critic validated on remote Container App.")


def _read_demo_jwt() -> str | None:
    if not DEMO_ENV.exists():
        return None
    for line in DEMO_ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANALYST_JWT="):
            return line.split("=", 1)[1].strip()
    return None


def _write_evidence(
    *,
    body: dict[str, object],
    audit_data: dict[str, object],
    nodes: list[str],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    prefix = EVIDENCE_DIR / f"azure-smoke-{timestamp}"

    markdown = str(body["document_markdown"])
    (prefix.with_suffix(".md")).write_text(markdown, encoding="utf-8")
    (prefix.with_suffix(".audit.json")).write_text(
        json.dumps(audit_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "action_sheet_id": body.get("action_sheet_id"),
        "run_id": body.get("run_id"),
        "audit_nodes": nodes,
        "critic_present": nodes[-1] == "critic" if nodes else False,
    }
    (prefix.with_suffix(".summary.json")).write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Evidence written: {prefix.name}.md/.audit.json/.summary.json")


if __name__ == "__main__":
    main()
