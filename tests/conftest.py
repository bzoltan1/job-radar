"""Pin tests to the committed example data so they never read a developer's personal *.local files."""

import os

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Must run before radar.config is imported: it resolves file paths at import time.
os.environ.update({
    "JOB_RADAR_PROFILE": os.path.join(_DATA, "profile.example.yaml"),
    "JOB_RADAR_TARGETS": os.path.join(_DATA, "targets.example.yaml"),
    "JOB_RADAR_TECH_STACK": os.path.join(_DATA, "tech_stack.example.yaml"),
    "JOB_RADAR_COUNTRIES": os.path.join(_DATA, "countries.yaml"),
    "JOB_RADAR_INTEL_DIR": os.path.join(_DATA, "nonexistent-intel"),
    "JOB_RADAR_DB": ":memory:",
    "CANDIDATE_COUNTRY": "Germany",
})
