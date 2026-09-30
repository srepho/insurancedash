"""Per-source status merged with registry source metadata."""

import json
import sys

from _common import ROOT

from ingest.registry import load

reg = load()
path = ROOT / "data" / "status.json"
status = json.loads(path.read_text())["sources"] if path.exists() else {}
out = {name: {**src, **status.get(name, {"status": "never_run"})} for name, src in reg.sources.items()}
json.dump(out, sys.stdout, indent=1)
