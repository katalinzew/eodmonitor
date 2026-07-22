import argparse
import hashlib
import json
import os
import re
import shutil
import sys

REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

from app.core.config import AGENT_PACKAGES_DIR
from app.core.database import get_conn


VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish(version, agent_path, activate):
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Version must use numeric semantic format, for example 1.6.0")
    source = os.path.abspath(agent_path)
    if not os.path.isfile(source):
        raise FileNotFoundError(source)

    release_dir = os.path.abspath(os.path.join(AGENT_PACKAGES_DIR, version))
    packages_root = os.path.abspath(AGENT_PACKAGES_DIR)
    if os.path.commonpath([packages_root, release_dir]) != packages_root:
        raise ValueError("Invalid release directory")
    os.makedirs(release_dir, exist_ok=True)

    destination = os.path.join(release_dir, "agent_eod.py")
    shutil.copy2(source, destination)
    manifest = {
        "files": [
            {
                "component": "agent",
                "source": "agent_eod.py",
                "sha256": sha256_file(destination),
            }
        ]
    }

    with get_conn() as conn:
        with conn.cursor() as cur:
            if activate:
                cur.execute("UPDATE agent_releases SET active = FALSE WHERE active = TRUE")
            cur.execute(
                """
                INSERT INTO agent_releases (version, manifest, active)
                VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (version)
                DO UPDATE SET manifest = EXCLUDED.manifest,
                              active = EXCLUDED.active
                RETURNING id
                """,
                (version, json.dumps(manifest), activate),
            )
            release_id = cur.fetchone()[0]

    print("Published release {0} (id={1}, active={2})".format(version, release_id, activate))
    print("Package directory: {0}".format(release_dir))


def main():
    parser = argparse.ArgumentParser(description="Publish an EOD Monitor agent release")
    parser.add_argument("--version", required=True)
    parser.add_argument("--agent", default="agent_eod.py")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    publish(args.version, args.agent, args.activate)


if __name__ == "__main__":
    main()
