"""Refresh Quarm world tables from SecretsOTheP/EQMacEmu (Linux/Docker).

INSTALL: Place this file at quarm_reference/quarm_sync.py in your Django project.
Requires Python 3.10+, mariadb and mariadb-dump on PATH (Debian package mariadb-client).
No additional Python packages. Django Q2 calls quarm_reference.quarm_sync.sync_quarm.

ENVIRONMENT (worker and manual-run container):
  QUARM_IMPORT_HOST=mariadb
  QUARM_IMPORT_PORT=3306
  QUARM_IMPORT_USER=quarm_import
  QUARM_IMPORT_PASSWORD=<secret>
  QUARM_SYNC_DIR=/app/quarm_sync_data
Optional GITHUB_TOKEN increases GitHub API limits (never sent to raw downloads).
Target is deliberately fixed to quarm_reference_db; do not use root credentials.
Give the import account privileges ONLY on that database. Keep the website's
read-only credentials unchanged. This connects directly, not via Django's alias.

PERSISTENCE: Mount the same host directory at /app/quarm_sync_data in every
container that runs this function. A Linux flock prevents concurrent imports;
all callers must use this same shared local-filesystem directory. Keep it outside
public media/static directories. Allow several GB free for backup and unpacking.

RUN with the project environment loaded:
  python manage.py shell -c "from quarm_reference.quarm_sync import sync_quarm; print(sync_quarm(dry_run=True))"
  python manage.py shell -c "from quarm_reference.quarm_sync import sync_quarm; print(sync_quarm())"
Or: python -m quarm_reference.quarm_sync --dry-run

SCHEDULE in Django admin > Django Q > Schedules:
  Function: quarm_reference.quarm_sync.sync_quarm
  Schedule type: Daily; Repeats: -1; Args/Kwargs: blank
  Next run: desired first run, using the admin's displayed timezone.
Merge Q_CLUSTER timeout=10800, retry=14400 into your existing configuration.
retry must exceed timeout for brokers that support retries. Keep qcluster running.
Daily uses the first-run time; review after DST if a fixed local hour matters.

BEHAVIOR: Newest timestamped quarm_*.tar.gz or quarm_*.sql.gz is selected.
A filename plus Git blob SHA identifies the imported version. Only the main
quarm_*.sql member is imported; the other archive scripts are not executed.
The script generates DROP TABLE statements only for tables defined by that dump.
Existing tables outside the dump remain untouched (including derived reference
tables, which this script does NOT rebuild). Matching world tables are replaced.

BACKUP/FAILURE: Makes a complete uncompressed SQL backup before changing tables;
keeps the newest seven after successful imports. Backup includes table locks
because the upstream data contains MyISAM tables. Run during a quiet period.
Import is NOT atomic: reference reads may fail or see partial data during import.
An import failure retains pending.json, the backup, and mariadb_error.log, and
blocks subsequent imports. Stop the schedule and restore the backup with a
privilege-scoped account using mariadb, then remove pending.json and state.json
and rerun. Restore does not remove newly introduced tables absent from the backup;
for exact recovery restore into a clean quarm_reference_db (recreate any custom
views/tables from backup). No automatic rollback is attempted.

Only enable the schedule after a manual import and checking your reference pages.
"""
from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)
REPO = "SecretsOTheP/EQMacEmu"
DIRECTORY = "utils/sql/database_full"
DATABASE = "quarm_reference_db"
NAME = re.compile(r"^quarm_(\d{4}-\d{2}-\d{2}-\d{2}_\d{2})\.(?:tar\.gz|sql\.gz)$")
CREATE = re.compile(rb"^CREATE TABLE `([A-Za-z0-9_]+)` \(")
MAX_ARCHIVE = 256 * 1024**2
MAX_SQL = 2 * 1024**3


def latest_dump(entries):
    candidates = []
    for entry in entries:
        match = NAME.fullmatch(entry.get("name", ""))
        if entry.get("type") == "file" and match:
            stamp = datetime.strptime(match[1], "%Y-%m-%d-%H_%M")
            candidates.append((stamp, entry["name"], entry))
    if not candidates:
        raise RuntimeError("No timestamped Quarm gzip dumps found")
    return max(candidates, key=lambda row: row[:2])[2]


def get_latest():
    headers = {"User-Agent": "quarm-reference-sync", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{REPO}/contents/{DIRECTORY}?ref=main"
    with urlopen(Request(url, headers=headers), timeout=60) as response:
        entries = json.load(response)
    if not isinstance(entries, list):
        raise RuntimeError("Unexpected GitHub directory response")
    return latest_dump(entries)


def bounded_copy(source, destination, limit):
    count = 0
    while chunk := source.read(1024 * 1024):
        count += len(chunk)
        if count > limit:
            raise RuntimeError("Download or unpacked SQL exceeds configured safety limit")
        destination.write(chunk)
    return count


def download(entry, path):
    # Fixed public host; API bearer token is not forwarded here.
    url = f"https://raw.githubusercontent.com/{REPO}/main/{DIRECTORY}/{quote(entry['name'])}"
    with urlopen(Request(url, headers={"User-Agent": "quarm-reference-sync"}), timeout=60) as response:
        with path.open("wb") as out:
            size = bounded_copy(response, out, MAX_ARCHIVE)
    if size != entry["size"]:
        raise RuntimeError("Download size changed; retry on the next run")
    digest = hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != entry["sha"]:
        raise RuntimeError("Git blob hash mismatch; refusing import")


def unpack(archive, sql, filename):
    if filename.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as bundle:
            members = [m for m in bundle.getmembers() if m.isfile()
                       and re.fullmatch(r"quarm_[0-9_:.-]+\.sql", PurePosixPath(m.name).name)]
            if len(members) != 1:
                raise RuntimeError("Expected exactly one Quarm world SQL member")
            # Stream to a fixed filename; never extract archive paths or links.
            with bundle.extractfile(members[0]) as source, sql.open("wb") as out:
                bounded_copy(source, out, MAX_SQL)
    else:
        with gzip.open(archive, "rb") as source, sql.open("wb") as out:
            bounded_copy(source, out, MAX_SQL)


def world_tables(sql):
    tables = []
    with sql.open("rb") as source:
        for line in source:
            match = CREATE.match(line)
            if match:
                tables.append(match[1].decode("ascii"))
            if re.match(rb"(?i)^\s*(USE\s|(?:CREATE|DROP)\s+DATABASE\b)", line):
                raise RuntimeError("Dump contains database-switching statements")
    if len(tables) != len(set(tables)) or not {"npc_types", "items", "zone"}.issubset(tables):
        raise RuntimeError("Unexpected world schema; refusing import")
    return tables


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as out:
        json.dump(value, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(path)


def option_value(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'


def write_credentials(path):
    values = {
        "host": os.environ.get("QUARM_IMPORT_HOST", "mariadb"),
        "port": str(int(os.environ.get("QUARM_IMPORT_PORT", "3306"))),
        "user": os.environ["QUARM_IMPORT_USER"],
        "password": os.environ["QUARM_IMPORT_PASSWORD"],
        "protocol": "tcp",
        "default-character-set": "utf8mb4",
    }
    with path.open("x", opener=lambda name, flags: os.open(name, flags, 0o600)) as out:
        out.write("[client]\n")
        for key, value in values.items():
            out.write(f"{key}={option_value(value)}\n")


def run_client(command, lock, error_log, *, source=None, output=None):
    # Inherit the flock descriptor so a surviving DB subprocess retains the lock
    # even if Django Q kills its Python parent. subprocess.run kills on timeout.
    with error_log.open("wb") as errors:
        result = subprocess.run(command, stdin=source, stdout=output or subprocess.DEVNULL,
                                stderr=errors, timeout=3600, pass_fds=(lock.fileno(),))
    if result.returncode:
        raise RuntimeError(f"MariaDB command failed ({result.returncode}); inspect {error_log}")


def sync_quarm(dry_run=False):
    """Django Q2 entry point. Exceptions are recorded as failed Q tasks."""
    root = Path(os.environ.get("QUARM_SYNC_DIR", "/app/quarm_sync_data"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "sync.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "already_running"}
        try:
            return _sync(root, lock, dry_run)
        except Exception:
            log.exception("Quarm refresh failed")
            raise


def _sync(root, lock, dry_run):
    state_path = root / "state.json"
    pending = root / "pending.json"
    if pending.exists() and not dry_run:
        raise RuntimeError(f"Previous import incomplete: inspect {pending} and recover before retrying")
    entry = get_latest()
    identity = {"name": entry["name"], "sha": entry["sha"]}
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if all(state.get(key) == value for key, value in identity.items()) and not dry_run:
        log.info("Quarm dump unchanged: %s", entry["name"])
        return {"status": "unchanged", **identity}
    log.info("Checking Quarm dump: %s", entry["name"])
    with tempfile.TemporaryDirectory(prefix="work-", dir=root) as folder:
        work = Path(folder)
        archive, sql = work / "source.gz", work / "world.sql"
        download(entry, archive)
        unpack(archive, sql, entry["name"])
        tables = world_tables(sql)
        if dry_run:
            return {"status": "validated_no_database_changes", **identity, "tables": tables}
        for executable in ("mariadb", "mariadb-dump"):
            if not shutil.which(executable):
                raise RuntimeError(f"Install mariadb-client: {executable} not on PATH")
        credentials = work / "client.cnf"
        write_credentials(credentials)
        defaults = f"--defaults-file={credentials}"
        errors = root / "mariadb_error.log"
        backup_dir = root / "backups"
        backup_dir.mkdir(exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = backup_dir / f"quarm_reference_db_{stamp}.sql"
        partial = backup.with_suffix(".partial")
        log.info("Backing up %s", DATABASE)
        with partial.open("wb") as out:
            run_client(["mariadb-dump", defaults, "--lock-all-tables", "--quick",
                        "--routines", "--events", "--triggers", "--hex-blob", DATABASE],
                       lock, errors, output=out)
            out.flush()
            os.fsync(out.fileno())
        if not partial.stat().st_size:
            raise RuntimeError("Empty backup; refusing import")
        partial.replace(backup)
        # Build our own reset list from the verified world file; do not run
        # drop_system.sql, which may remove unrelated tables.
        prepared = work / "import.sql"
        with prepared.open("wb") as out:
            out.write(b"SET FOREIGN_KEY_CHECKS=0;\n")
            for table in tables:
                out.write(f"DROP TABLE IF EXISTS `{table}`;\n".encode())
            with sql.open("rb") as source:
                shutil.copyfileobj(source, out)
            out.write(b"\nSET FOREIGN_KEY_CHECKS=1;\n")
        atomic_json(pending, {**identity, "backup": str(backup), "started": stamp})
        log.info("Replacing %s world tables in %s", len(tables), DATABASE)
        with prepared.open("rb") as source:
            run_client(["mariadb", defaults, "--binary-mode", "--local-infile=0", DATABASE],
                       lock, errors, source=source)
        # Basic post-import checks; leave the failure marker if any check fails.
        checks = b"SELECT COUNT(*) FROM npc_types; SELECT COUNT(*) FROM items; SELECT COUNT(*) FROM zone;"
        check_sql, check_out = work / "check.sql", work / "check.txt"
        check_sql.write_bytes(checks)
        with check_sql.open("rb") as source, check_out.open("wb") as out:
            run_client(["mariadb", defaults, "--batch", "--skip-column-names", DATABASE],
                       lock, errors, source=source, output=out)
        counts = [int(value) for value in check_out.read_text().split()]
        if len(counts) != 3 or min(counts) <= 0:
            raise RuntimeError("Post-import world-table checks failed; backup retained")
        atomic_json(state_path, {**identity, "imported_at": datetime.now(timezone.utc).isoformat(),
                                 "backup": str(backup), "counts": counts})
        pending.unlink()
        for old in sorted(backup_dir.glob("quarm_reference_db_*.sql"), reverse=True)[7:]:
            old.unlink()
        log.info("Quarm refresh complete: %s", entry["name"])
        return {"status": "updated", **identity, "backup": str(backup),
                "npc_types": counts[0], "items": counts[1], "zone": counts[2]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(sync_quarm(dry_run=args.dry_run), indent=2))
