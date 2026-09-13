"""Capture real clean-rag /search responses for the headroom Stage 1 measurement."""
import json, urllib.request, pathlib, time

SERVER = "http://127.0.0.1:8613/search"
OUT = pathlib.Path(__file__).parent / "payloads_wire"

PROJECTS = {
    "assets-backend": "/Users/geoffniehaus/repos/shop-todaymechanic/assets/backend",
    "assets-messages": "/Users/geoffniehaus/repos/messages-todaymechanic/assets/messages",
    "reputation-ontology": "/Users/geoffniehaus/repos/reputation-ontology",
}

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

manifest = []
for pname, ppath in PROJECTS.items():
    for i, q in enumerate(QUERIES):
        try:
            t0 = time.time()
            wire, resp = post(q, ppath)
            dt = time.time() - t0
        except Exception as e:
            print(f"SKIP {pname}/{i}: {type(e).__name__}: {e}")
            continue
        raw = wire        # measure what the server actually sends, not a re-indent
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
print(f"\n{len(manifest)} payloads, {sum(m['bytes'] for m in manifest):,} bytes total")
