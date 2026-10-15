"""Memory rehearsal: how much each container needs while analysing the worst clips allowed.

Run against the smoke stack (scripts/smoke_docker.sh with KEEP=1), optionally with memory caps
(deploy/docker-compose.memory.yml), and give it the clips to analyse:

    python3 scripts/memory_rehearsal.py https://localhost:8443 --mailpit http://localhost:8025 \\
        clip1.mp4 clip2.mov --label "no caps"

For each clip it restarts the worker (so its peak starts from zero), uploads the clip,
waits for the analysis, and reads every container's peak memory from the kernel's cgroup
counter (memory.peak, which includes short-lived children such as the pose process and
ffmpeg). It prints a Markdown table. Standard library only, like smoke_test.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import PASSWORD, Client, check, latest_link, wait_until  # noqa: E402

PROJECT = "serve-smoke"
SERVICES = ("web", "api", "worker", "postgres")
CONTENT_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


def containers() -> dict[str, str]:
    """Service name -> container id, for the smoke project."""
    out = subprocess.run(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}",
                          "--format", '{{.ID}} {{.Label "com.docker.compose.service"}}'],
                         capture_output=True, text=True, check=True).stdout
    return {svc: cid for cid, svc in (line.split() for line in out.splitlines()) if svc in SERVICES}


def peak_mb(container: str) -> float:
    raw = subprocess.run(["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.peak"],
                         capture_output=True, text=True, check=True).stdout
    return int(raw) / 2**20


def limit_mb(container: str) -> str:
    raw = subprocess.run(["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.max"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return "none" if raw == "max" else f"{int(raw) / 2**20:.0f}"


def restart_worker() -> None:
    subprocess.run(["docker", "restart", containers()["worker"]], check=True, capture_output=True)


def analyse(c: Client, clip: Path, timeout_s: float) -> tuple[str, float]:
    body = {"hand": "right", "filename": clip.name, "content_type": CONTENT_TYPES[clip.suffix.lower()],
            "size_bytes": clip.stat().st_size}
    created = c.json("POST", "/api/analyses", body, 201)
    analysis_id, upload = created["analysis"]["id"], created["upload"]
    status, _, data = c.call("PUT", upload["url"], raw=clip.read_bytes(), headers=upload["headers"])
    check(status in (200, 204), f"upload -> {status}: {data[:200]!r}")
    started = time.monotonic()
    c.json("POST", f"/api/analyses/{analysis_id}/start", expect=202)

    def finished():
        summary = c.json("GET", f"/api/analyses/{analysis_id}")
        return summary if summary["status"] in ("succeeded", "failed") else None

    summary = wait_until(f"{clip.name} to finish", finished, timeout_s=timeout_s, every_s=3)
    outcome = summary["status"] if summary["status"] == "succeeded" else f"failed: {summary['error']['code']}"
    return outcome, time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("clips", nargs="+", type=Path)
    parser.add_argument("--mailpit", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()

    c = Client(args.base, insecure=True)
    email = f"memory-{uuid.uuid4().hex[:8]}@example.com"
    c.json("POST", "/api/auth/signup", {"email": email, "password": PASSWORD, "accept_terms": True,
                                        "username": f"mem_{uuid.uuid4().hex[:12]}"}, 201)
    c.json("POST", "/api/auth/verify-email", {"token": latest_link(args.mailpit, email, "/verify-email")}, 204)

    ids = containers()
    limits = {svc: limit_mb(ids[svc]) for svc in SERVICES}
    rows = []
    for clip in args.clips:
        restart_worker()
        wait_until("the worker", lambda: "worker" in containers(), timeout_s=60)
        time.sleep(3)
        outcome, seconds = analyse(c, clip, args.timeout)
        ids = containers()
        peaks = {svc: peak_mb(ids[svc]) for svc in SERVICES}
        rows.append((clip.name, outcome, seconds, peaks))
        print(f"{clip.name}: {outcome} in {seconds:.0f}s, peaks (MB) "
              + json.dumps({k: round(v) for k, v in peaks.items()}), flush=True)
    c.json("DELETE", "/api/auth/me", {"password": PASSWORD}, 204)

    print(f"\n### {args.label or 'Memory rehearsal'}\n")
    print("Limits (MB): " + ", ".join(f"{svc} {limits[svc]}" for svc in SERVICES) + "\n")
    print("| Clip | Result | Time | Worker peak | API peak | Postgres peak | Caddy peak | All containers |")
    print("|---|---|---|---|---|---|---|---|")
    for name, outcome, seconds, p in rows:
        total = sum(p.values())
        print(f"| {name} | {outcome} | {seconds:.0f} s | {p['worker']:.0f} MB | {p['api']:.0f} MB | "
              f"{p['postgres']:.0f} MB | {p['web']:.0f} MB | {total:.0f} MB |")


if __name__ == "__main__":
    main()
