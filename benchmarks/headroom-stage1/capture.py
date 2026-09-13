"""Capture real clean-rag /search responses for the headroom Stage 1 measurement."""
import json, os, urllib.request, pathlib, time

BASE = os.environ.get("CLEAN_RAG_URL", "http://127.0.0.1:8613").rstrip("/")
SERVER = f"{BASE}/search"
OUT = pathlib.Path(__file__).parent / "payloads_wire"

# How many indexed projects to sample, largest-index first.
N_PROJECTS = int(os.environ.get("STAGE1_N_PROJECTS", "3"))


def discover_projects(n=N_PROJECTS):
    """Pick the n best-indexed projects from the running server.

    Deliberately NOT hardcoded: absolute paths are local to whoever ran the
    capture, and this is a public repo. Override with STAGE1_PROJECTS as a
    comma-separated list of absolute paths to pin an exact set.
    """
    pinned = os.environ.get("STAGE1_PROJECTS", "").strip()
    if pinned:
        return {pathlib.Path(p).name: p for p in
                (x.strip() for x in pinned.split(",")) if p}
    with urllib.request.urlopen(f"{BASE}/projects", timeout=60) as r:
        entries = json.loads(r.read().decode())["projects"]
    ranked = sorted(entries.items(),
                    key=lambda kv: -(kv[1].get("chunks_created") or 0))
    return {k: v["project_path"] for k, v in ranked[:n]
            if v.get("project_path")}


# The kind of query researcher/swiper actually issue on a real change.
QUERIES = [
    "authentication and authorization check on endpoint",
    "input validation at system boundary",
    "error handling and logger.error in catch block",
    "database query parameterized sql",
    "how are tests structured for the service layer",
    "configuration loading and environment variables",
]

def post(query, path, mode="both", limit=10):
    body = json.dumps({"query": query, "sources": [f"project:{path}"],
                       "mode": mode, "limit": limit}).encode()
    req = urllib.request.Request(SERVER, data=body,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        wire = r.read().decode()          # EXACT bytes the server sent
    return wire, json.loads(wire)

def capture_all(projects=None):
    """Capture every query against every project. Overwrites OUT."""
    projects = projects if projects is not None else discover_projects()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for pname, ppath in projects.items():
        for i, q in enumerate(QUERIES):
            try:
                t0 = time.time()
                wire, resp = post(q, ppath)
                dt = time.time() - t0
            except Exception as e:
                print(f"SKIP {pname}/{i}: {type(e).__name__}: {e}")
                continue
            raw = wire    # measure what the server actually sends, not a re-indent
            n = len(resp.get("results", [])) if isinstance(resp, dict) else len(resp)
            if n == 0:
                print(f"empty  {pname}/{i}  '{q[:40]}'")
                continue
            fn = OUT / f"search_{pname}_{i}.json"
            fn.write_text(raw)
            manifest.append({"file": fn.name, "project": pname, "query": q,
                             "results": n, "bytes": len(raw), "latency_s": round(dt, 2)})
            print(f"saved  {fn.name}  {n} results  {len(raw):,} bytes  {dt:.1f}s")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\n{len(manifest)} payloads, "
          f"{sum(m['bytes'] for m in manifest):,} bytes total")
    return manifest


# Importing this module must never hit the network or overwrite a recorded
# capture: discovery and the capture loop both run only when invoked directly.
if __name__ == "__main__":
    capture_all()
