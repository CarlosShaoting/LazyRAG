import subprocess
from pathlib import Path

OPENSEARCH_HOME = Path("/home/mnt/cuishaoting/opensearch-2.12.0")

process = subprocess.Popen(
    ["bash", "-c", "./bin/opensearch"],
    cwd=OPENSEARCH_HOME
)

print("OpenSearch started PID:", process.pid)