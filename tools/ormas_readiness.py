"""Unimplemented base for the frozen diagnostic task."""
import json
import sys
print(json.dumps({"schema_version":"ormas.readiness-report.v1","profile_id":None,"catalog_digest":None,"ruleset":"2026-10-04.1","repository":{"status":"unknown","detected_locks":[],"source":{"files":None,"bytes":None,"inventory_mode":"unavailable"},"environment_names":[],"findings":[{"code":"unimplemented"}]},"capacity":{"status":"unknown","findings":[]},"live_admission":"not_established"},sort_keys=True))
sys.exit(3)
