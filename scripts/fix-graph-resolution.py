"""Re-run graph edge resolution on an existing graph.db with updated classifier rules."""
import sys, sqlite3, pathlib, traceback

# Add mcp-rag-server/src to path relative to this script's location
_repo_root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root / "mcp-rag-server" / "src"))

from rag_server.core.project import project_index_dir, ALL_CODE_EXTENSIONS
from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
from rag_server.indexing.engine import _find_go_modules

if len(sys.argv) < 2:
    print("Usage: fix-graph-resolution.py <project_path>")
    sys.exit(1)
PROJECT = sys.argv[1]
idx_dir = project_index_dir(PROJECT)
db_path = str(idx_dir / "graph.db")

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM edges WHERE target_file = ''")
before_empty = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM edges WHERE target_file = '_external_'")
before_ext = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM edges WHERE target_file NOT IN ('','_external_')")
before_res = cur.fetchone()[0]
conn.close()
print(f"Before: resolved={before_res}, external={before_ext}, empty={before_empty}")

root = pathlib.Path(PROJECT)
file_map = {}
for p in root.rglob("*"):
    if p.is_file() and p.suffix in ALL_CODE_EXTENSIONS:
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
            stem = rel.rsplit(".", 1)[0] if "." in rel else rel
            file_map[rel] = rel
            file_map[stem] = rel
        except Exception:  # pragma: no cover
            pass  # pragma: no cover
print(f"File map: {len(file_map)} entries")

go_prefixes = _find_go_modules(PROJECT)
print(f"Go prefixes: {sorted(go_prefixes)[:5]}")

graph = SQLiteGraphStore(db_path)
try:
    count = graph.resolve_target_files(file_map, go_prefixes)
    print(f"Newly resolved to project files: {count}")
except Exception:
    traceback.print_exc()

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM edges WHERE target_file = ''")
after_empty = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM edges WHERE target_file = '_external_'")
after_ext = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM edges WHERE target_file NOT IN ('','_external_')")
after_res = cur.fetchone()[0]
conn.close()
nex = after_res + after_empty
print(f"After: resolved={after_res}, external={after_ext}, empty={after_empty}")
if nex:
    print(f"Effective rate: {after_res/nex*100:.1f}% of non-external edges resolved")
