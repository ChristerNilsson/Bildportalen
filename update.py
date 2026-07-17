from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    RefreshError = Exception
    GoogleAuthRequest = None
    Credentials = None
    InstalledAppFlow = None


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT

LOG_FILE_NAME = f"{datetime.now().year}.log"
LOG_FILE = ROOT / LOG_FILE_NAME
LOCK_FILE = ROOT / "update.lock"
LOCK_STALE_SECONDS = 2 * 60 * 60


PHOTOGRAPHERS_FILE = ROOT / "photographers.json"
PHOTOS_FILE = ROOT / "photos.json"
PHOTOGRAPHER_DATA_DIR = ROOT / "photographers"
DATABASE_FILE = ROOT / "bildportalen.sqlite"
DATABASE_DOC_FILE = ROOT / "bildportalen_database.txt"
OAUTH_CREDENTIALS_FILE = ROOT / "credentials.json"
OAUTH_TOKEN_FILE = ROOT / "token.json"
OAUTH_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
OUTPUT_SCHEMA_VERSION = 2
IMAGE_MIME_PREFIX = "image/"
PDF_MIME_TYPE = "application/pdf"
LINK_FILE_EXTENSIONS = (".pdf", ".txt")
SUPPORTED_FILE_EXTENSIONS = (*LINK_FILE_EXTENSIONS, ".url")
TOP_LEVEL_ROOTS_NORMALIZED = {
    "klubbar": "Klubbar",
    "0000 klubbar": "Klubbar",
}
YEAR_SECTION_ALIASES = {
    "0000 evenemang": "Evenemang",
    "0000 diverse": "Diverse",
}
GOOGLE_DRIVE_FOLDER = "application/vnd.google-apps.folder"
USER_AGENT = "Mozilla/5.0 BildbankenForAll/1.0"
GOOGLE_DRIVE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY", "")
OAUTH_TOKEN = ""
DRIVE_JSON_STATS: dict[str, dict[str, int]] = {}


def log(message: str, format = "%H:%M:%S") -> None:  # %Y-%m-%d eller %H:%M:%S
    timestamp = datetime.now().strftime(format)
    line = f"{timestamp} {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def commit_and_push_updates() -> None:
    run_git("add", LOG_FILE_NAME)
    run_git("add", str(PHOTOS_FILE.relative_to(REPO_ROOT)))

    diff = run_git("diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        log("Inga Git-ändringar att committa.")
        return
    if diff.returncode != 1:
        raise subprocess.CalledProcessError(
            diff.returncode,
            diff.args,
            output=diff.stdout,
            stderr=diff.stderr,
        )

    run_git("commit", "-m", "Update photo data")
    run_git("push")



@dataclass(frozen=True)
class DriveItem:
    id: str
    name: str
    mime_type: str
    modified_time: str = ""
    taken_time: int = 0

    @property
    def is_folder(self) -> bool:
        return self.mime_type == GOOGLE_DRIVE_FOLDER

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith(IMAGE_MIME_PREFIX)

    @property
    def is_link_file(self) -> bool:
        return self.name.lower().endswith(LINK_FILE_EXTENSIONS)

    @property
    def is_url_file(self) -> bool:
        return self.name.lower().endswith(".url")


@dataclass(frozen=True)
class DriveMetadata:
    id: str
    name: str
    mime_type: str
    modified_time: str = ""
    taken_time: int = 0
    parents: tuple[str, ...] = ()

    @property
    def is_folder(self) -> bool:
        return self.mime_type == GOOGLE_DRIVE_FOLDER


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_json_with_legacy(path: Path, legacy_path: Path, default: Any) -> Any:
    if path.exists():
        return read_json(path, default)
    return read_json(legacy_path, default)


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_json_file(path: Path, data: Any) -> None:
    if data and not path.exists():
        write_json(path, data)
        log(f"Skapade {path.name}.")


def log_step(message: str) -> None:
    log(f"{message}")


def log_detail(message: str) -> None:
    log(f" {message}")


def reset_drive_json_stats() -> None:
    DRIVE_JSON_STATS.clear()


def drive_json_stat_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith("/changes") or "/changes" in path:
        return "changes"
    if path.endswith("/files"):
        return "files-list"
    if "/files/" in path:
        query = parse_qs(parsed.query)
        if query.get("alt") == ["media"]:
            return "files-media"
        return "files-metadata"
    return path.rsplit("/", 1)[-1] or "drive-json"


def record_drive_json_bytes(url: str, byte_count: int) -> None:
    key = drive_json_stat_key(url)
    stats = DRIVE_JSON_STATS.setdefault(key, {"calls": 0, "bytes": 0})
    stats["calls"] += 1
    stats["bytes"] += byte_count


def log_drive_json_stats() -> None:
    if not DRIVE_JSON_STATS:
        log_detail("Drive JSON: 0 anrop, 0 bytes.")
        return

    total_calls = sum(stats["calls"] for stats in DRIVE_JSON_STATS.values())
    total_bytes = sum(stats["bytes"] for stats in DRIVE_JSON_STATS.values())
    parts = [
        f"{key}={stats['calls']} anrop/{stats['bytes']} bytes"
        for key, stats in sorted(DRIVE_JSON_STATS.items())
    ]
    log_detail(f"Drive JSON: {total_calls} anrop, {total_bytes} bytes ({'; '.join(parts)}).")


def log_traceback(error: BaseException) -> None:
    for line in traceback.format_exception(type(error), error, error.__traceback__):
        for row in line.rstrip().splitlines():
            log_detail(row)


def start_log_section() -> None:
    print()
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write("\n")


def acquire_update_lock() -> bool:
    try:
        lock_age = time.time() - LOCK_FILE.stat().st_mtime
    except FileNotFoundError:
        lock_age = 0
    else:
        if lock_age < LOCK_STALE_SECONDS:
            lock_text = LOCK_FILE.read_text(encoding="utf-8", errors="replace").strip()
            log(f"Avbryter: {LOCK_FILE.name} finns redan. En uppdatering verkar redan köra. {lock_text}")
            return False
        log(f"Tar bort gammal {LOCK_FILE.name} efter {lock_age / 60:.1f} minuter.")
        LOCK_FILE.unlink()

    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        log(f"Avbryter: {LOCK_FILE.name} skapades av en annan process.")
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(f"pid={os.getpid()} start={datetime.now().isoformat(timespec='seconds')}\n")
    return True


def release_update_lock() -> None:
    try:
        lock_text = LOCK_FILE.read_text(encoding="utf-8", errors="replace")
        if not lock_text.startswith(f"pid={os.getpid()} "):
            return
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def open_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS photographer_cache (
            photographer_key TEXT PRIMARY KEY,
            photos_json TEXT NOT NULL,
            changes_json TEXT NOT NULL,
            drive_entries_json TEXT NOT NULL DEFAULT '[]',
            photo_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(photographer_cache)").fetchall()
    }
    if "drive_entries_json" not in columns:
        connection.execute(
            "ALTER TABLE photographer_cache ADD COLUMN drive_entries_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "photo_count" not in columns:
        connection.execute(
            "ALTER TABLE photographer_cache ADD COLUMN photo_count INTEGER NOT NULL DEFAULT 0"
        )
        connection.execute(
            """
            UPDATE photographer_cache
            SET photo_count = (
                CASE
                    WHEN photos_json = '' THEN 0
                    ELSE photo_count
                END
            )
            """
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def write_database_documentation(connection: sqlite3.Connection) -> None:
    lines = [
        "Bildportalen databas",
        "====================",
        "",
        f"Fil: {DATABASE_FILE.name}",
        "Typ: SQLite, lokal cache för update.py.",
        "",
        "Syfte",
        "-----",
        "Databasen ersätter tidigare cachefiler i photographers/*.json och",
        "photographers/*.changes.json. Den publika filen är fortfarande photos.json.",
        "Databasen används för att undvika full omläsning av Google Drive när Drive",
        "Changes API visar att inget har ändrats eller när en ändring kan patchas",
        "inkrementellt.",
        "",
        "Tabeller",
        "--------",
    ]

    table_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    for (table_name,) in table_rows:
        lines.extend(["", table_name, "-" * len(table_name)])
        columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        for _cid, name, column_type, notnull, default_value, primary_key in columns:
            flags: list[str] = []
            if primary_key:
                flags.append("PRIMARY KEY")
            if notnull:
                flags.append("NOT NULL")
            if default_value is not None:
                flags.append(f"DEFAULT {default_value}")
            suffix = f" ({', '.join(flags)})" if flags else ""
            lines.append(f"- {name}: {column_type or 'ANY'}{suffix}")

    lines.extend(
        [
            "",
            "photographer_cache",
            "------------------",
            "- photographer_key: Nyckeln från photographers.json, t.ex. LOAH_26.",
            "- photos_json: Fotografens deltrad i samma format som motsvarande del av photos.json.",
            "- changes_json: Drive Changes-state med schemaVersion, pageToken och trackedIds.",
            "- drive_entries_json: Index över Drive-objekt: id, name, mimeType, modifiedTime, takenTime och path.",
            "- photo_count: Antal bilder for snabb totalsummering utan att parse:a photos_json.",
            "- updated_at: Lokal tidpunkt när cacheposten senast skrevs.",
            "",
            "meta",
            "----",
            "Allmän nyckel/värde-tabell för framtida metadata. Den används inte aktivt i nuläget.",
            "",
            "Viktiga JSON-format",
            "-------------------",
            "changes_json:",
            "  {",
            "    \"schemaVersion\": 2,",
            "    \"pageToken\": \"...\",",
            "    \"trackedIds\": [\"drive-id\", \"...\"]",
            "  }",
            "",
            "drive_entries_json:",
            "  [",
            "    {",
            "      \"id\": \"drive-id\",",
            "      \"name\": \"fil-eller-katalog\",",
            "      \"mimeType\": \"image/jpeg\",",
            "      \"modifiedTime\": \"2026-01-01T12:00:00.000Z\",",
            "      \"takenTime\": 3970000000,",
            "      \"path\": \"2026/Turnering/bild.jpg\"",
            "    }",
            "  ]",
            "",
            "Inkrementella uppdateringar",
            "---------------------------",
            "- Filnamnsändring, ny fil, filborttagning och katalognamnsändring kan patchas direkt.",
            "- Osäkra fall, t.ex. flyttade kataloger eller okänd parent-kedja, faller tillbaka till full rescan.",
            "- photos.json skrivs bara om när den publika strukturen faktiskt ändras.",
            "",
        ]
    )

    DATABASE_DOC_FILE.write_text("\n".join(lines), encoding="utf-8-sig")


def migrate_legacy_photographer_files(connection: sqlite3.Connection, photographer_keys: set[str]) -> None:
    if not PHOTOGRAPHER_DATA_DIR.exists():
        return

    migrated = 0
    for photographer_key in sorted(photographer_keys, key=str.casefold):
        exists = connection.execute(
            "SELECT 1 FROM photographer_cache WHERE photographer_key = ?",
            (photographer_key,),
        ).fetchone()
        if exists:
            continue

        photographer_file = PHOTOGRAPHER_DATA_DIR / f"{photographer_key}.json"
        changes_file = PHOTOGRAPHER_DATA_DIR / f"{photographer_key}.changes.json"
        if not photographer_file.exists():
            continue

        photographer_photos = read_json(photographer_file, {})
        changes_state = read_json(changes_file, {}) if changes_file.exists() else {}
        save_photographer_cache(connection, photographer_key, photographer_photos, changes_state, [])
        migrated += 1

    if migrated:
        log_step(f"Migrerade {migrated} fotografcacher till {DATABASE_FILE.name}.")


def get_photographer_cache(
    connection: sqlite3.Connection,
    photographer_key: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    row = connection.execute(
        "SELECT photos_json, changes_json, drive_entries_json FROM photographer_cache WHERE photographer_key = ?",
        (photographer_key,),
    ).fetchone()
    if row is None:
        return {}, {}, []
    photos = json_loads(row[0], {})
    changes_state = json_loads(row[1], {})
    drive_entries = json_loads(row[2], [])
    if photos and not drive_entries:
        drive_entries = drive_entries_from_photos(photos)
    return photos, changes_state, drive_entries


def has_saved_drive_entries(connection: sqlite3.Connection, photographer_key: str) -> bool:
    row = connection.execute(
        "SELECT length(drive_entries_json) FROM photographer_cache WHERE photographer_key = ?",
        (photographer_key,),
    ).fetchone()
    return bool(row and row[0] and row[0] > 2)


def backfill_photo_counts(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT photographer_key, photos_json FROM photographer_cache WHERE photo_count = 0"
    ).fetchall()
    changed = False
    for photographer_key, photos_json in rows:
        photos = json_loads(photos_json, {})
        photo_count = count_photos(photos)
        if photo_count:
            connection.execute(
                "UPDATE photographer_cache SET photo_count = ? WHERE photographer_key = ?",
                (photo_count, photographer_key),
            )
            changed = True
    if changed:
        connection.commit()


def save_photographer_cache(
    connection: sqlite3.Connection,
    photographer_key: str,
    photographer_photos: dict[str, Any],
    changes_state: dict[str, Any],
    drive_entries: list[dict[str, Any]],
) -> None:
    connection.execute(
        """
        INSERT INTO photographer_cache (photographer_key, photos_json, changes_json, drive_entries_json, photo_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(photographer_key) DO UPDATE SET
            photos_json = excluded.photos_json,
            changes_json = excluded.changes_json,
            drive_entries_json = excluded.drive_entries_json,
            photo_count = excluded.photo_count,
            updated_at = excluded.updated_at
        """,
        (
            photographer_key,
            json_dumps(photographer_photos),
            json_dumps(changes_state),
            json_dumps(drive_entries),
            count_photos(photographer_photos),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    connection.commit()


def update_photographer_change_cache(
    connection: sqlite3.Connection,
    photographer_key: str,
    changes_state: dict[str, Any],
    drive_entries: list[dict[str, Any]] | None = None,
) -> None:
    if drive_entries is None:
        connection.execute(
            """
            UPDATE photographer_cache
            SET changes_json = ?, updated_at = ?
            WHERE photographer_key = ?
            """,
            (
                json_dumps(changes_state),
                datetime.now().isoformat(timespec="seconds"),
                photographer_key,
            ),
        )
    else:
        connection.execute(
            """
            UPDATE photographer_cache
            SET changes_json = ?, drive_entries_json = ?, updated_at = ?
            WHERE photographer_key = ?
            """,
            (
                json_dumps(changes_state),
                json_dumps(drive_entries),
                datetime.now().isoformat(timespec="seconds"),
                photographer_key,
            ),
        )
    connection.commit()


def drive_entries_from_photos(node: Any, path: list[str] | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = []
    if isinstance(node, dict):
        entries: list[dict[str, Any]] = []
        for name, value in node.items():
            entries.extend(drive_entries_from_photos(value, [*path, name]))
        return entries
    if not path:
        return []

    name = path[-1]
    item_path = "/".join(path)
    if isinstance(node, list) and len(node) >= 3:
        return [
            {
                "id": node[0],
                "name": name,
                "mimeType": "image/jpeg",
                "modifiedTime": "",
                "takenTime": node[2],
                "path": item_path,
            }
        ]
    if isinstance(node, str):
        if name.lower().endswith(".pdf"):
            mime_type = PDF_MIME_TYPE
        elif name.lower().endswith(".txt"):
            mime_type = "text/plain"
        else:
            mime_type = "application/octet-stream"
        return [
            {
                "id": node,
                "name": name,
                "mimeType": mime_type,
                "modifiedTime": "",
                "takenTime": 0,
                "path": item_path,
            }
        ]
    return []


def delete_removed_photographer_caches(connection: sqlite3.Connection, photographer_keys: set[str]) -> list[dict[str, Any]]:
    rows = connection.execute("SELECT photographer_key, photos_json FROM photographer_cache").fetchall()
    removed_trees: list[dict[str, Any]] = []
    for photographer_key, photos_json in rows:
        if photographer_key in photographer_keys:
            continue
        removed_trees.append(json_loads(photos_json, {}))
        connection.execute(
            "DELETE FROM photographer_cache WHERE photographer_key = ?",
            (photographer_key,),
        )
        log_detail(f"Tog bort cache för saknad fotograf {photographer_key}.")
    if removed_trees:
        connection.commit()
    return removed_trees


def load_oauth_token() -> str:
    if not OAUTH_CREDENTIALS_FILE.exists():
        return ""
    if Credentials is None or GoogleAuthRequest is None or InstalledAppFlow is None:
        log("credentials.json finns men OAuth-biblioteken saknas. Kör: python -m pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        return ""

    creds = None
    if OAUTH_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(OAUTH_TOKEN_FILE))

    has_required_scopes = bool(creds and creds.has_scopes(OAUTH_SCOPES))
    if creds and creds.expired and creds.refresh_token and has_required_scopes:
        try:
            creds.refresh(GoogleAuthRequest())
        except RefreshError as error:
            log(f"OAuth-token kunde inte förnyas: {error}. Begär nytt godkännande.")
            creds = None

    if not creds or not creds.valid or not has_required_scopes:
        if creds and not has_required_scopes:
            log("OAuth-token saknar läsbehörighet för filinnehåll. Begär nytt godkännande.")
        flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CREDENTIALS_FILE), OAUTH_SCOPES)
        creds = flow.run_local_server(port=0)
        OAUTH_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        log(f"Skapade {OAUTH_TOKEN_FILE.name}.")

    return creds.token or ""


def drive_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", parsed.path)
    if match:
        return match.group(1)
    match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
    if match:
        return match.group(1)
    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return query_id[0]
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", url):
        return url
    return None


def drive_folder_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", parsed.path)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", url):
        return url
    return None


def drive_file_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
    if match:
        return match.group(1)
    query_id = parse_qs(parsed.query).get("id")
    if query_id and "uc" in parsed.path:
        return query_id[0]
    return None


def drive_file_fallback_name(photographer_key: str, photographer: list[Any]) -> str:
    if len(photographer) >= 3 and isinstance(photographer[2], str) and photographer[2].strip():
        return photographer[2].strip()
    if photographer_key.casefold() == "help":
        return "Help.pdf"
    return ""


def cached_drive_changes(
    page_token: str,
    changes_cache: dict[str, tuple[list[dict[str, Any]], str]],
) -> tuple[list[dict[str, Any]], str]:
    if page_token not in changes_cache:
        changes_cache[page_token] = list_drive_changes(page_token)
    return changes_cache[page_token]


def photographer_has_drive_changes(
    changes_state: dict[str, Any],
    changes_cache: dict[str, tuple[list[dict[str, Any]], str]],
) -> bool:
    if changes_state.get("schemaVersion") != OUTPUT_SCHEMA_VERSION:
        return True

    page_token = changes_state.get("pageToken", "")
    if not page_token:
        return True

    tracked_ids = set(changes_state.get("trackedIds", []))
    if not tracked_ids:
        return True

    try:
        changes, new_page_token = cached_drive_changes(page_token, changes_cache)
    except RuntimeError as error:
        log(f"Drive Changes API misslyckades: {error}. Gör full kontroll.")
        return True

    for change in changes:
        file_id = change.get("fileId", "")
        file_data = change.get("file") or {}
        parents = set(file_data.get("parents", []))
        if file_id in tracked_ids or parents.intersection(tracked_ids):
            return True

    if new_page_token and new_page_token != page_token:
        changes_state["pageToken"] = new_page_token
    return False


def list_drive_changes(page_token: str) -> tuple[list[dict[str, Any]], str]:
    changes: list[dict[str, Any]] = []
    token = page_token
    new_start_page_token = ""

    while True:
        query = {
            "pageToken": token,
            "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,parents,trashed,imageMediaMetadata(time)))",
            "pageSize": "1000",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        data = fetch_drive_json("https://www.googleapis.com/drive/v3/changes?" + urlencode(query))
        changes.extend(data.get("changes", []))
        token = data.get("nextPageToken", "")
        new_start_page_token = data.get("newStartPageToken", new_start_page_token)
        if not token:
            return changes, new_start_page_token or page_token


def build_changes_state(folder_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    tracked_ids = {folder_id}
    for entry in entries:
        tracked_ids.add(entry.get("id", ""))
    tracked_ids.discard("")

    return {
        "schemaVersion": OUTPUT_SCHEMA_VERSION,
        "pageToken": get_drive_start_page_token(),
        "trackedIds": sorted(tracked_ids),
    }


def get_drive_start_page_token() -> str:
    data = fetch_drive_json(
        "https://www.googleapis.com/drive/v3/changes/startPageToken?"
        + urlencode({"fields": "startPageToken", "supportsAllDrives": "true"})
    )
    return data.get("startPageToken", "")


def add_drive_file(
    photos: dict[str, Any],
    photographer_key: str,
    file_id: str,
    drive_entries: list[dict[str, Any]],
    fallback_name: str = "",
) -> int:
    try:
        item = get_drive_file_item(file_id, fallback_name)
    except RuntimeError as error:
        log(f"Hoppar över Drive-fil {file_id}: {error}")
        return 0

    drive_entries.append(
        {
            "id": item.id,
            "name": item.name,
            "mimeType": item.mime_type,
            "modifiedTime": item.modified_time,
            "takenTime": item.taken_time,
            "path": item.name,
        }
    )

    if item.is_url_file:
        try:
            target_url = read_url_file(item.id)
        except RuntimeError as error:
            log_detail(f"Hoppar över {item.name}: {error}")
            return 0
        link_name = re.sub(r"\.url$", "", item.name, flags=re.IGNORECASE)
        insert_file(photos, [], link_name, target_url, preserve_top_level=True)
        return 1
    if item.is_link_file:
        insert_file(photos, [], item.name, item.id, preserve_top_level=True)
        return 1
    if item.is_image:
        insert_file(photos, [], item.name, [item.id, photographer_key, item.taken_time])
        return 1

    log_detail(f"Hoppar över {item.name}: filtypen {item.mime_type!r} stöds inte.")
    return 0


def get_drive_file_item(file_id: str, fallback_name: str = "") -> DriveItem:
    if OAUTH_TOKEN or GOOGLE_DRIVE_API_KEY:
        query = {
            "fields": "id,name,mimeType,modifiedTime,imageMediaMetadata(time)",
            "supportsAllDrives": "true",
        }
        if not OAUTH_TOKEN:
            query["key"] = GOOGLE_DRIVE_API_KEY
        data = fetch_drive_json(f"https://www.googleapis.com/drive/v3/files/{file_id}?" + urlencode(query))
        name = repair_text(data.get("name", ""))
        mime_type = data.get("mimeType", "")
        modified_time = data.get("modifiedTime", "")
        image_time = (data.get("imageMediaMetadata") or {}).get("time", "")
        taken_time = drive_image_taken_time(image_time, modified_time)
        if name and mime_type:
            return DriveItem(file_id, name, mime_type, modified_time, taken_time)

    if fallback_name:
        mime_type = PDF_MIME_TYPE if fallback_name.lower().endswith(".pdf") else "application/octet-stream"
        return DriveItem(file_id, fallback_name, mime_type)

    raise RuntimeError("kunde inte läsa filmetadata.")


def get_drive_metadata(file_id: str) -> DriveMetadata:
    query = {
        "fields": "id,name,mimeType,modifiedTime,parents,imageMediaMetadata(time)",
        "supportsAllDrives": "true",
    }
    if not OAUTH_TOKEN:
        query["key"] = GOOGLE_DRIVE_API_KEY
    data = fetch_drive_json(f"https://www.googleapis.com/drive/v3/files/{file_id}?" + urlencode(query))
    item_id = data.get("id", file_id)
    name = repair_text(data.get("name", ""))
    mime_type = data.get("mimeType", "")
    modified_time = data.get("modifiedTime", "")
    image_time = (data.get("imageMediaMetadata") or {}).get("time", "")
    taken_time = drive_image_taken_time(image_time, modified_time)
    parents = tuple(data.get("parents", []))
    if not item_id or not name or not mime_type:
        raise RuntimeError(f"kunde inte läsa Drive-metadata för {file_id}.")
    return DriveMetadata(item_id, name, mime_type, modified_time, taken_time, parents)


def drive_item_from_metadata(metadata: DriveMetadata) -> DriveItem:
    return DriveItem(
        metadata.id,
        metadata.name,
        metadata.mime_type,
        metadata.modified_time,
        metadata.taken_time,
    )


def add_drive_folder(
    photos: dict[str, Any],
    photographer_key: str,
    folder_id: str,
    path: list[str],
    drive_entries: list[dict[str, Any]],
    visited: set[str] | None = None,
    root_folder_name: str | None = None,
) -> int:
    if visited is None:
        visited = set()
    if folder_id in visited:
        return 0
    visited.add(folder_id)

    if root_folder_name is None and not path:
        root_folder_name = get_drive_folder_name(folder_id)
        drive_entries.append(
            {
                "id": folder_id,
                "name": root_folder_name,
                "mimeType": GOOGLE_DRIVE_FOLDER,
                "modifiedTime": "",
                "takenTime": 0,
                "path": "",
            }
        )

    try:
        items = list_drive_folder(folder_id)
    except RuntimeError as error:
        log(f"Hoppar över Drive-folder {folder_id}: {error}")
        return 0

    changed = 0
    for item in sorted(items, key=lambda entry: (not entry.is_folder, entry.name.lower())):
        drive_entries.append(
            {
                "id": item.id,
                "name": item.name,
                "mimeType": item.mime_type,
                "modifiedTime": item.modified_time,
                "takenTime": item.taken_time,
                "path": "/".join([*path, item.name]),
            }
        )
        if item.is_folder:
            changed += add_drive_folder(
                photos,
                photographer_key,
                item.id,
                [*path, item.name],
                drive_entries,
                visited,
                root_folder_name,
            )
        elif item.is_image:
            insert_file(
                photos,
                path,
                item.name,
                [item.id, photographer_key, item.taken_time],
                root_folder_name=root_folder_name,
            )
            changed += 1
        elif item.is_url_file:
            try:
                target_url = read_url_file(item.id)
            except RuntimeError as error:
                log_detail(f"Hoppar över {item.name}: {error}")
                continue
            link_name = re.sub(r"\.url$", "", item.name, flags=re.IGNORECASE)
            insert_file(
                photos,
                path,
                link_name,
                target_url,
                preserve_top_level=True,
                root_folder_name=root_folder_name,
            )
            changed += 1
        elif item.is_link_file:
            insert_file(
                photos,
                path,
                item.name,
                item.id,
                preserve_top_level=True,
                root_folder_name=root_folder_name,
            )
            changed += 1
    return changed


def list_drive_folder(folder_id: str) -> list[DriveItem]:
    if OAUTH_TOKEN or GOOGLE_DRIVE_API_KEY:
        try:
            return list_drive_folder_api(folder_id)
        except RuntimeError as error:
            log(f"Drive API misslyckades för {folder_id}: {error}. Faller tillbaka till HTML.")

    urls = [
        f"https://drive.google.com/embeddedfolderview?id={folder_id}#list",
        f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing",
    ]

    errors: list[str] = []
    for url in urls:
        try:
            body = fetch_text(url)
        except RuntimeError as error:
            errors.append(str(error))
            continue

        items = [item for item in parse_drive_items(body) if item.id != folder_id]
        if items:
            return items

    detail = "; ".join(errors) if errors else "Drive-sidan innehöll inga parsade poster."
    raise RuntimeError(detail)


def list_drive_folder_api(folder_id: str) -> list[DriveItem]:
    items: list[DriveItem] = []
    page_token = ""
    while True:
        query = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,imageMediaMetadata(time))",
            "pageSize": "1000",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if not OAUTH_TOKEN:
            query["key"] = GOOGLE_DRIVE_API_KEY
        if page_token:
            query["pageToken"] = page_token

        url = "https://www.googleapis.com/drive/v3/files?" + urlencode(query)
        data = fetch_drive_json(url)
        for entry in data.get("files", []):
            item_id = entry.get("id", "")
            name = repair_text(entry.get("name", ""))
            mime_type = entry.get("mimeType", "")
            if item_id and name and mime_type:
                image_time = (entry.get("imageMediaMetadata") or {}).get("time", "")
                modified_time = entry.get("modifiedTime", "")
                taken_time = drive_image_taken_time(image_time, modified_time)
                items.append(DriveItem(item_id, name, mime_type, modified_time, taken_time))

        page_token = data.get("nextPageToken", "")
        if not page_token:
            return items


def get_drive_folder_name(folder_id: str) -> str:
    if OAUTH_TOKEN or GOOGLE_DRIVE_API_KEY:
        query = {
            "fields": "name",
            "supportsAllDrives": "true",
        }
        if not OAUTH_TOKEN:
            query["key"] = GOOGLE_DRIVE_API_KEY
        data = fetch_drive_json(
            f"https://www.googleapis.com/drive/v3/files/{folder_id}?" + urlencode(query)
        )
        name = data.get("name", "")
        if name:
            return repair_text(name)

    try:
        body = fetch_text(f"https://drive.google.com/drive/folders/{folder_id}")
    except RuntimeError:
        return ""
    match = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
    if match:
        title = clean_html(match.group(1))
        title = re.sub(r"\s*-\s*Google Drive\s*$", "", title, flags=re.IGNORECASE).strip()
        if title:
            return title
    return ""


def fetch_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(request(url), timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(str(error)) from error


def fetch_drive_json(url: str) -> dict[str, Any]:
    try:
        headers = {"User-Agent": USER_AGENT}
        if OAUTH_TOKEN:
            headers["Authorization"] = f"Bearer {OAUTH_TOKEN}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            body = response.read()
            record_drive_json_bytes(url, len(body))
            return json.loads(body.decode("utf-8"))
    except HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except OSError:
            detail = str(error)
        raise RuntimeError(detail) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(str(error)) from error


def fetch_drive_text(url: str) -> str:
    try:
        headers = {"User-Agent": USER_AGENT}
        if OAUTH_TOKEN:
            headers["Authorization"] = f"Bearer {OAUTH_TOKEN}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            return response.read().decode("utf-8-sig", errors="replace")
    except HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except OSError:
            detail = str(error)
        raise RuntimeError(detail) from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(str(error)) from error


def read_url_file(file_id: str) -> str:
    if OAUTH_TOKEN or GOOGLE_DRIVE_API_KEY:
        query = {"alt": "media"}
        if not OAUTH_TOKEN:
            query["key"] = GOOGLE_DRIVE_API_KEY
        try:
            content = fetch_drive_text(
                f"https://www.googleapis.com/drive/v3/files/{file_id}?" + urlencode(query)
            )
        except RuntimeError as api_error:
            try:
                content = fetch_public_drive_file(file_id)
            except RuntimeError:
                raise api_error
    else:
        content = fetch_public_drive_file(file_id)

    lines = content.splitlines()
    if len(lines) < 2:
        raise RuntimeError("url-filen saknar en andra rad.")

    target = re.sub(r"^\s*URL\s*=\s*", "", lines[1], flags=re.IGNORECASE).strip()
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("url-filens andra rad innehåller ingen giltig http- eller https-länk.")
    return target


def fetch_public_drive_file(file_id: str) -> str:
    return fetch_text(
        "https://drive.google.com/uc?" + urlencode({"export": "download", "id": file_id})
    )


def fetch_text(url: str) -> str:
    try:
        with urlopen(request(url), timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(str(error)) from error


def request(url: str) -> Request:
    return Request(url, headers={"User-Agent": USER_AGENT})


def parse_drive_items(body: str) -> list[DriveItem]:
    text = html.unescape(body)
    text = text.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\u002F", "/")

    items: dict[str, DriveItem] = {}
    parse_embedded_folder_view(text, items)
    parse_rendered_drive_list(text, items)
    parse_drive_bootstrap_data(text, items)
    return list(items.values())


def parse_embedded_folder_view(text: str, items: dict[str, DriveItem]) -> None:
    link_pattern = re.compile(
        r'<a[^>]+href="(?P<href>[^"]*(?:/file/d/|/drive/folders/|[?&]id=)[^"]+)"[^>]*>(?P<label>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in link_pattern.finditer(text):
        href = html.unescape(match.group("href"))
        name = repair_text(clean_html(match.group("label")))
        item_id = drive_id_from_url(href)
        if not item_id or not name:
            continue
        if "/folders/" in href:
            mime_type = GOOGLE_DRIVE_FOLDER
        elif name.lower().endswith(SUPPORTED_FILE_EXTENSIONS):
            mime_type = PDF_MIME_TYPE
        else:
            mime_type = "image/jpeg"
        items[item_id] = DriveItem(item_id, name, mime_type)


def parse_rendered_drive_list(text: str, items: dict[str, DriveItem]) -> None:
    id_then_label = re.compile(
        r'data-id="(?P<id>[A-Za-z0-9_-]{10,})"(?:(?!data-id=).){0,2500}?'
        r'aria-label="(?P<label>[^"]+) (?P<kind>Image|Folder|PDF|Text|File|Unknown) Shared"',
        re.DOTALL,
    )
    label_then_id = re.compile(
        r'aria-label="(?P<label>[^"]+) (?P<kind>Image|Folder|PDF|Text|File|Unknown) Shared"(?:(?!aria-label=).){0,2500}?'
        r'data-id="(?P<id>[A-Za-z0-9_-]{10,})"',
        re.DOTALL,
    )
    for pattern in (id_then_label, label_then_id):
        for match in pattern.finditer(text):
            item_id = match.group("id")
            name = repair_text(html.unescape(match.group("label")).strip())
            if match.group("kind") == "Folder":
                mime_type = GOOGLE_DRIVE_FOLDER
            elif match.group("kind") == "PDF":
                mime_type = PDF_MIME_TYPE
            elif name.lower().endswith((".url", ".txt")):
                mime_type = "application/octet-stream"
            else:
                mime_type = "image/jpeg"
            if name:
                items[item_id] = DriveItem(item_id, name, mime_type)


def parse_drive_bootstrap_data(text: str, items: dict[str, DriveItem]) -> None:
    # Google Drive embeds folder contents in large JavaScript arrays. The exact schema changes,
    # so this intentionally extracts only stable-looking id/name/mime triples.
    triple_pattern = re.compile(
        r'\["(?P<id>[A-Za-z0-9_-]{10,})"\s*,\s*"(?P<name>(?:[^"\\]|\\.)+)"\s*,\s*"(?P<mime>[^"]+)"',
        re.DOTALL,
    )
    for match in triple_pattern.finditer(text):
        add_bootstrap_item(match, items)

    alternate_pattern = re.compile(
        r'\["(?P<id>[A-Za-z0-9_-]{10,})"[^\[]+?"(?P<name>(?:[^"\\]|\\.)+)"[^\[]+?"(?P<mime>image/[^"]+|application/pdf|text/plain|application/octet-stream|application/vnd\.google-apps\.folder)"',
        re.DOTALL,
    )
    for match in alternate_pattern.finditer(text):
        add_bootstrap_item(match, items)


def add_bootstrap_item(match: re.Match[str], items: dict[str, DriveItem]) -> None:
    item_id = match.group("id")
    name = repair_text(decode_js_string(match.group("name")))
    mime_type = decode_js_string(match.group("mime"))
    if name and (
        mime_type.startswith(IMAGE_MIME_PREFIX)
        or mime_type in (PDF_MIME_TYPE, GOOGLE_DRIVE_FOLDER)
        or name.lower().endswith(SUPPORTED_FILE_EXTENSIONS)
    ):
        items[item_id] = DriveItem(item_id, name, mime_type)


def decode_js_string(value: str) -> str:
    return bytes(value, "utf-8").decode("unicode_escape")


def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value))).strip()


def repair_text(value: str) -> str:
    mojibake_markers = ("\u00c3\u0192", "\u00c3\u201a")
    if not any(marker in value for marker in mojibake_markers):
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value


def timestamp_seconds_since_1900(value: str) -> int:
    if not value:
        return 0

    parsed: datetime | None = None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(value.strip(), pattern)
                break
            except ValueError:
                pass

    if parsed is None:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    epoch = datetime(1900, 1, 1, tzinfo=timezone.utc)
    return round((parsed.astimezone(timezone.utc) - epoch).total_seconds())


def drive_image_taken_time(image_time: str, modified_time: str) -> int:
    taken_time = timestamp_seconds_since_1900(image_time)
    if not taken_time:
        return 0

    modified_timestamp = timestamp_seconds_since_1900(modified_time)
    if modified_timestamp and abs(taken_time - modified_timestamp) <= 1:
        return 0
    return taken_time


def insert_file(
    photos: dict[str, Any],
    path: list[str],
    filename: str,
    value: Any,
    preserve_top_level: bool = False,
    root_folder_name: str | None = None,
) -> None:
    if preserve_top_level and not path:
        photos[filename] = value
        return

    year, parts = tree_parts([*path, filename], root_folder_name)
    node = photos.setdefault(year, {})
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def contains_okand(node: Any) -> bool:
    if isinstance(node, dict):
        if "okand" in node:
            return True
        return any(contains_okand(child) for child in node.values())
    return False


def merge_tree(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            child = target.setdefault(key, {})
            merge_tree(child, value)
        else:
            target[key] = value


def file_paths(node: Any, path: list[str] | None = None) -> set[str]:
    if path is None:
        path = []
    if isinstance(node, dict):
        paths: set[str] = set()
        for name, value in node.items():
            paths.update(file_paths(value, [*path, name]))
        return paths
    if path:
        return {"/".join(path)}
    return set()


def remove_leaf_path(node: dict[str, Any], path: list[str]) -> None:
    if not path:
        return

    parents: list[tuple[dict[str, Any], str]] = []
    current: Any = node
    for part in path[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        parents.append((current, part))
        current = current[part]

    if not isinstance(current, dict):
        return
    current.pop(path[-1], None)

    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)
        else:
            break


def remove_tree(target: dict[str, Any], source: dict[str, Any]) -> None:
    for path in sorted(file_paths(source), key=lambda value: value.count("/"), reverse=True):
        remove_leaf_path(target, path.split("/"))


def set_leaf_path(node: dict[str, Any], path: list[str], value: Any) -> None:
    if not path:
        return
    current = node
    for part in path[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[path[-1]] = value


def get_leaf_path(node: Any, path: list[str]) -> Any:
    current = node
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def find_leaf_path_by_drive_id(node: Any, drive_id: str, path: list[str] | None = None) -> list[str] | None:
    if path is None:
        path = []
    if isinstance(node, dict):
        for key, value in node.items():
            found = find_leaf_path_by_drive_id(value, drive_id, [*path, key])
            if found is not None:
                return found
        return None
    if isinstance(node, list) and node and node[0] == drive_id:
        return path
    if isinstance(node, str) and node == drive_id:
        return path
    return None


def photo_leaf_name(item_name: str, item_mime_type: str) -> str:
    if item_name.lower().endswith(".url"):
        return re.sub(r"\.url$", "", item_name, flags=re.IGNORECASE)
    return item_name


def drive_item_value(photographer_key: str, item: DriveItem) -> Any:
    if item.is_url_file:
        return read_url_file(item.id)
    if item.is_link_file:
        return item.id
    if item.is_image:
        return [item.id, photographer_key, item.taken_time]
    raise RuntimeError(f"filtypen {item.mime_type!r} stöds inte.")


def drive_item_from_change(file_id: str, file_data: dict[str, Any], old_entry: dict[str, Any]) -> DriveItem:
    name = repair_text(file_data.get("name", "")) or old_entry.get("name", "")
    mime_type = file_data.get("mimeType", "") or old_entry.get("mimeType", "")
    modified_time = file_data.get("modifiedTime", "") or old_entry.get("modifiedTime", "")
    image_time = (file_data.get("imageMediaMetadata") or {}).get("time", "")
    taken_time = drive_image_taken_time(image_time, modified_time)
    if not taken_time:
        taken_time = int(old_entry.get("takenTime", 0) or 0)
    return DriveItem(file_id, name, mime_type, modified_time, taken_time)


def photos_path_from_drive_path(drive_path: str, item: DriveItem, root_folder_name: str = "") -> list[str]:
    parts = [part for part in drive_path.split("/") if part]
    if parts:
        parts[-1] = photo_leaf_name(item.name, item.mime_type)
    else:
        parts = [photo_leaf_name(item.name, item.mime_type)]
    year, tree_path = tree_parts(parts, root_folder_name or None)
    return [year, *tree_path]


def drive_entry_for_item(item: DriveItem, drive_path: str) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "mimeType": item.mime_type,
        "modifiedTime": item.modified_time,
        "takenTime": item.taken_time,
        "path": drive_path,
    }


def drive_entry_for_folder(metadata: DriveMetadata, drive_path: str) -> dict[str, Any]:
    return {
        "id": metadata.id,
        "name": metadata.name,
        "mimeType": metadata.mime_type,
        "modifiedTime": metadata.modified_time,
        "takenTime": 0,
        "path": drive_path,
    }


def is_drive_path_descendant(path: str, folder_path: str) -> bool:
    return bool(folder_path) and path.startswith(folder_path + "/")


def apply_folder_rename(
    photos: dict[str, Any],
    entry_by_id: dict[str, dict[str, Any]],
    folder_entry: dict[str, Any],
    new_name: str,
    modified_time: str,
    root_folder_name: str,
) -> tuple[bool, str, str]:
    old_folder_path = folder_entry.get("path", "")
    if not old_folder_path:
        return False, "", ""

    parent_path = old_folder_path.rsplit("/", 1)[0] if "/" in old_folder_path else ""
    new_folder_path = "/".join(part for part in (parent_path, new_name) if part)
    if new_folder_path == old_folder_path:
        folder_entry["name"] = new_name
        folder_entry["modifiedTime"] = modified_time
        return True, old_folder_path, new_folder_path

    descendants = [
        entry
        for entry in entry_by_id.values()
        if is_drive_path_descendant(entry.get("path", ""), old_folder_path)
    ]
    if not descendants:
        folder_entry.update({"name": new_name, "modifiedTime": modified_time, "path": new_folder_path})
        return True, old_folder_path, new_folder_path

    moves: list[tuple[list[str], list[str], Any, dict[str, Any], str]] = []
    for entry in descendants:
        old_drive_path = entry.get("path", "")
        new_drive_path = new_folder_path + old_drive_path[len(old_folder_path):]
        item = DriveItem(
            entry.get("id", ""),
            entry.get("name", ""),
            entry.get("mimeType", ""),
            entry.get("modifiedTime", ""),
            int(entry.get("takenTime", 0) or 0),
        )
        if item.is_folder:
            continue

        old_photos_path = photos_path_from_drive_path(old_drive_path, item, root_folder_name)
        value = get_leaf_path(photos, old_photos_path)
        if value is None:
            found_path = find_leaf_path_by_drive_id(photos, item.id)
            if found_path is None:
                return False, "", ""
            old_photos_path = found_path
            value = get_leaf_path(photos, old_photos_path)
        new_photos_path = photos_path_from_drive_path(new_drive_path, item, root_folder_name)
        moves.append((old_photos_path, new_photos_path, value, entry, new_drive_path))

    for old_photos_path, _new_photos_path, _value, _entry, _new_drive_path in moves:
        remove_leaf_path(photos, old_photos_path)
    for _old_photos_path, new_photos_path, value, entry, new_drive_path in moves:
        set_leaf_path(photos, new_photos_path, value)
        entry["path"] = new_drive_path

    for entry in descendants:
        if entry.get("mimeType") == GOOGLE_DRIVE_FOLDER:
            old_drive_path = entry.get("path", "")
            if is_drive_path_descendant(old_drive_path, old_folder_path):
                entry["path"] = new_folder_path + old_drive_path[len(old_folder_path):]

    folder_entry.update({"name": new_name, "modifiedTime": modified_time, "path": new_folder_path})
    return True, old_folder_path, new_folder_path


def resolve_parent_entry(
    parent_id: str,
    entry_by_id: dict[str, dict[str, Any]],
    tracked_ids: set[str],
) -> dict[str, Any] | None:
    if parent_id in entry_by_id:
        return entry_by_id[parent_id]

    chain: list[DriveMetadata] = []
    current_id = parent_id
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        metadata = get_drive_metadata(current_id)
        if not metadata.is_folder:
            return None
        chain.append(metadata)

        known_parent = next((parent for parent in metadata.parents if parent in entry_by_id), "")
        if known_parent:
            parent_entry = entry_by_id[known_parent]
            parent_path = parent_entry.get("path", "")
            for folder_metadata in reversed(chain):
                folder_path = "/".join(part for part in (parent_path, folder_metadata.name) if part)
                entry = drive_entry_for_folder(folder_metadata, folder_path)
                entry_by_id[folder_metadata.id] = entry
                tracked_ids.add(folder_metadata.id)
                parent_path = folder_path
            return entry_by_id[parent_id]

        root_parent = next((parent for parent in metadata.parents if parent in tracked_ids), "")
        if root_parent:
            parent_path = ""
            for folder_metadata in reversed(chain):
                folder_path = "/".join(part for part in (parent_path, folder_metadata.name) if part)
                entry = drive_entry_for_folder(folder_metadata, folder_path)
                entry_by_id[folder_metadata.id] = entry
                tracked_ids.add(folder_metadata.id)
                parent_path = folder_path
            return entry_by_id[parent_id]

        if len(metadata.parents) != 1:
            return None
        current_id = metadata.parents[0]

    return None


def relevant_drive_changes(changes: list[dict[str, Any]], tracked_ids: set[str]) -> list[dict[str, Any]]:
    relevant_ids = set(tracked_ids)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    changed = True
    while changed:
        changed = False
        for change in changes:
            file_id = change.get("fileId", "")
            if file_id in selected_ids:
                continue
            file_data = change.get("file") or {}
            parents = set(file_data.get("parents", []))
            if file_id in relevant_ids or parents.intersection(relevant_ids):
                selected.append(change)
                selected_ids.add(file_id)
                relevant_ids.add(file_id)
                changed = True

    return selected


def apply_drive_changes_incremental(
    photographer_key: str,
    old_photographer_photos: dict[str, Any],
    changes_state: dict[str, Any],
    drive_entries: list[dict[str, Any]],
    changes_cache: dict[str, tuple[list[dict[str, Any]], str]],
) -> tuple[bool, dict[str, Any], dict[str, Any], list[dict[str, Any]], bool, list[str]]:
    if changes_state.get("schemaVersion") != OUTPUT_SCHEMA_VERSION:
        return False, old_photographer_photos, changes_state, drive_entries, False, []
    page_token = changes_state.get("pageToken", "")
    if not page_token or not drive_entries:
        return False, old_photographer_photos, changes_state, drive_entries, False, []

    try:
        changes, new_page_token = cached_drive_changes(page_token, changes_cache)
    except RuntimeError as error:
        log(f"Drive Changes API misslyckades: {error}. Gör full kontroll.")
        return False, old_photographer_photos, changes_state, drive_entries, False, []

    tracked_ids = set(changes_state.get("trackedIds", []))
    filtered_changes = relevant_drive_changes(changes, tracked_ids)
    if not filtered_changes:
        new_changes_state = dict(changes_state)
        if new_page_token and new_page_token != page_token:
            new_changes_state["pageToken"] = new_page_token
        return True, old_photographer_photos, new_changes_state, drive_entries, False, []

    folder_mime = GOOGLE_DRIVE_FOLDER
    ordered_changes = sorted(
        filtered_changes,
        key=lambda change: (0 if (change.get("file") or {}).get("mimeType") == folder_mime else 1),
    )

    new_photos = json_loads(json_dumps(old_photographer_photos), {})
    new_entries = json_loads(json_dumps(drive_entries), [])
    new_entry_by_id = {entry.get("id", ""): entry for entry in new_entries if entry.get("id")}
    new_tracked_ids = set(tracked_ids)
    root_entries = [entry for entry in new_entries if entry.get("path", "") == "" and entry.get("mimeType") == GOOGLE_DRIVE_FOLDER]
    root_folder_name = root_entries[0].get("name", "") if root_entries else ""
    changed = False
    change_log: list[str] = []

    for change in ordered_changes:
        file_id = change.get("fileId", "")
        file_data = change.get("file") or {}
        old_entry = new_entry_by_id.get(file_id)
        if old_entry is None:
            if change.get("removed") or file_data.get("trashed"):
                continue

            parent_ids = list(file_data.get("parents", []))
            if len(parent_ids) != 1:
                if file_id in new_tracked_ids:
                    return False, old_photographer_photos, changes_state, drive_entries, False, []
                continue
            if parent_ids[0] not in new_tracked_ids and parent_ids[0] not in new_entry_by_id:
                continue
            parent_entry = resolve_parent_entry(parent_ids[0], new_entry_by_id, new_tracked_ids)
            if parent_entry is None:
                if file_id in new_tracked_ids or parent_ids[0] in new_tracked_ids:
                    return False, old_photographer_photos, changes_state, drive_entries, False, []
                continue
            if parent_entry.get("mimeType") != GOOGLE_DRIVE_FOLDER:
                return False, old_photographer_photos, changes_state, drive_entries, False, []

            item = drive_item_from_change(file_id, file_data, {})
            if item.is_folder:
                folder_path = "/".join(part for part in (parent_entry.get("path", ""), item.name) if part)
                folder_metadata = DriveMetadata(
                    item.id,
                    item.name,
                    item.mime_type,
                    item.modified_time,
                    item.taken_time,
                    tuple(parent_ids),
                )
                new_entry_by_id[file_id] = drive_entry_for_folder(folder_metadata, folder_path)
                new_tracked_ids.add(file_id)
                changed = True
                continue
            if not (item.is_image or item.is_link_file or item.is_url_file):
                return False, old_photographer_photos, changes_state, drive_entries, False, []

            parent_path = parent_entry.get("path", "")
            drive_path = "/".join(part for part in (parent_path, item.name) if part)
            photos_path = photos_path_from_drive_path(drive_path, item, root_folder_name)
            value = drive_item_value(photographer_key, item)
            set_leaf_path(new_photos, photos_path, value)
            new_entry = drive_entry_for_item(item, drive_path)
            new_entry_by_id[file_id] = new_entry
            new_tracked_ids.add(file_id)
            changed = True
            continue

        if old_entry.get("mimeType") == GOOGLE_DRIVE_FOLDER:
            if change.get("removed") or file_data.get("trashed"):
                return False, old_photographer_photos, changes_state, drive_entries, False, []

            parent_ids = list(file_data.get("parents", []))
            if len(parent_ids) != 1:
                return False, old_photographer_photos, changes_state, drive_entries, False, []
            parent_entry = resolve_parent_entry(parent_ids[0], new_entry_by_id, new_tracked_ids)
            if parent_entry is None:
                return False, old_photographer_photos, changes_state, drive_entries, False, []
            old_folder_path = old_entry.get("path", "")
            old_parent_path = old_folder_path.rsplit("/", 1)[0] if "/" in old_folder_path else ""
            if parent_entry.get("path", "") != old_parent_path:
                return False, old_photographer_photos, changes_state, drive_entries, False, []

            new_name = repair_text(file_data.get("name", "")) or old_entry.get("name", "")
            modified_time = file_data.get("modifiedTime", "") or old_entry.get("modifiedTime", "")
            folder_renamed, old_folder_path, new_folder_path = apply_folder_rename(
                new_photos,
                new_entry_by_id,
                old_entry,
                new_name,
                modified_time,
                root_folder_name,
            )
            if not folder_renamed:
                return False, old_photographer_photos, changes_state, drive_entries, False, []
            if old_folder_path != new_folder_path:
                change_log.append(f"~ {old_folder_path} -> {new_folder_path}")
            changed = True
            continue

        old_leaf_path = find_leaf_path_by_drive_id(new_photos, file_id)
        if old_leaf_path is None:
            return False, old_photographer_photos, changes_state, drive_entries, False, []

        if change.get("removed") or file_data.get("trashed"):
            remove_leaf_path(new_photos, old_leaf_path)
            new_entries = [entry for entry in new_entries if entry.get("id") != file_id]
            new_entry_by_id.pop(file_id, None)
            new_tracked_ids.discard(file_id)
            changed = True
            continue

        item = drive_item_from_change(file_id, file_data, old_entry)
        if item.is_folder:
            return False, old_photographer_photos, changes_state, drive_entries, False, []
        if not (item.is_image or item.is_link_file or item.is_url_file):
            return False, old_photographer_photos, changes_state, drive_entries, False, []

        old_drive_path = old_entry.get("path", item.name)
        drive_parent_path = old_drive_path.rsplit("/", 1)[0] if "/" in old_drive_path else ""
        new_drive_path = "/".join(part for part in (drive_parent_path, item.name) if part)
        new_leaf_path = photos_path_from_drive_path(new_drive_path, item, root_folder_name)
        value = drive_item_value(photographer_key, item)

        remove_leaf_path(new_photos, old_leaf_path)
        set_leaf_path(new_photos, new_leaf_path, value)
        old_entry.update(drive_entry_for_item(item, new_drive_path))
        changed = True

    new_changes_state = dict(changes_state)
    new_changes_state["pageToken"] = new_page_token or page_token
    new_changes_state["trackedIds"] = sorted(new_tracked_ids)
    new_entries = sorted(new_entry_by_id.values(), key=lambda entry: (entry.get("path", ""), entry.get("id", "")))
    return True, new_photos, new_changes_state, new_entries, changed, change_log


def build_photos_from_database(
    connection: sqlite3.Connection,
    photographer_keys: list[str],
) -> dict[str, Any]:
    photos: dict[str, Any] = {}
    for photographer_key in photographer_keys:
        photographer_photos, _changes_state, _drive_entries = get_photographer_cache(connection, photographer_key)
        merge_tree(photos, photographer_photos)
    return photos


def count_database_photos(connection: sqlite3.Connection, photographer_keys: list[str]) -> int:
    if not photographer_keys:
        return 0
    placeholders = ",".join("?" for _key in photographer_keys)
    row = connection.execute(
        f"SELECT COALESCE(SUM(photo_count), 0) FROM photographer_cache WHERE photographer_key IN ({placeholders})",
        photographer_keys,
    ).fetchone()
    return int(row[0] or 0)


def log_file_changes(old_tree: dict[str, Any], new_tree: dict[str, Any]) -> None:
    old_paths = file_paths(old_tree)
    new_paths = file_paths(new_tree)
    for path in sorted(new_paths - old_paths, key=str.casefold):
        log_detail(f"+ {path}")
    for path in sorted(old_paths - new_paths, key=str.casefold):
        log_detail(f"- {path}")


def tree_parts(parts: list[str], root_folder_name: str | None = None) -> tuple[str, list[str]]:
    if parts:
        first = parts[0].strip()
        normalized_first = first.casefold()
        if normalized_first in TOP_LEVEL_ROOTS_NORMALIZED:
            return TOP_LEVEL_ROOTS_NORMALIZED[normalized_first], parts[1:]

    for index, part in enumerate(parts):
        normalized = part.strip().casefold()
        if normalized in TOP_LEVEL_ROOTS_NORMALIZED:
            return TOP_LEVEL_ROOTS_NORMALIZED[normalized], parts[index + 1:]

    if root_folder_name is not None:
        normalized_root = root_folder_name.strip().casefold()
        if normalized_root in TOP_LEVEL_ROOTS_NORMALIZED:
            return TOP_LEVEL_ROOTS_NORMALIZED[normalized_root], parts

    year = next((part for part in parts if re.fullmatch(r"(?!0000)\d{4}", part)), None)
    if year is None:
        year = next(
            (
                match.group("year")
                for part in parts
                if (match := re.match(r"^(?!0000)(?P<year>\d{4})(?:\D|$)", part))
            ),
            None,
        )
    if year is None:
        dated = next((part[:4] for part in parts if re.match(r"\d{4}-\d{2}-\d{2}", part)), None)
        year = dated or "okand"
    if parts and parts[0] == year:
        parts = parts[1:]
    parts = [YEAR_SECTION_ALIASES.get(part.strip().casefold(), part) for part in parts]
    return year, parts


def count_photos(node: Any) -> int:
    if isinstance(node, list):
        return 1
    if isinstance(node, dict):
        return sum(count_photos(child) for child in node.values())
    return 0


def count_entries(node: Any) -> int:
    if isinstance(node, (list, str)):
        return 1
    if isinstance(node, dict):
        return sum(count_entries(child) for child in node.values())
    return 0


def update_photographer_cache(
    connection: sqlite3.Connection,
    photographer_key: str,
    photographer: list[Any],
    changes_cache: dict[str, tuple[list[dict[str, Any]], str]],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if not isinstance(photographer, list) or len(photographer) < 2:
        log(f"Hoppar över {photographer_key}: fotografposten saknar Drive-url.")
        return {}, {}, False

    source_url = photographer[1]
    folder_id = drive_folder_id_from_url(source_url)
    file_id = drive_file_id_from_url(source_url)
    if folder_id is None and file_id is None:
        folder_id = drive_id_from_url(source_url)
    if folder_id is None and file_id is None:
        log(f"Hoppar över {photographer_key}: kan inte läsa Drive-id ur {source_url!r}.")
        return {}, {}, False

    log_step(photographer_key)
    old_photographer_photos, changes_state, old_drive_entries = get_photographer_cache(connection, photographer_key)
    has_drive_entries = has_saved_drive_entries(connection, photographer_key)

    if OAUTH_TOKEN and old_photographer_photos and changes_state:
        handled_incrementally, incremental_photos, incremental_changes_state, incremental_drive_entries, changed, change_log = (
            apply_drive_changes_incremental(
                photographer_key,
                old_photographer_photos,
                changes_state,
                old_drive_entries,
                changes_cache,
            )
        )
        if handled_incrementally and not changed and contains_okand(old_photographer_photos):
            handled_incrementally = False
            changed = True
            log_detail(f"Omgenererar {photographer_key} eftersom cachen innehåller okand.")
        if handled_incrementally:
            if changed:
                log_detail(f"Uppdaterade databascache för {photographer_key} via Drive Changes.")
                if change_log:
                    for line in change_log:
                        log_detail(line)
                else:
                    log_file_changes(old_photographer_photos, incremental_photos)
                save_photographer_cache(
                    connection,
                    photographer_key,
                    incremental_photos,
                    incremental_changes_state,
                    incremental_drive_entries,
                )
            elif has_drive_entries:
                update_photographer_change_cache(
                    connection,
                    photographer_key,
                    incremental_changes_state,
                )
            else:
                update_photographer_change_cache(
                    connection,
                    photographer_key,
                    incremental_changes_state,
                    incremental_drive_entries,
                )
            return old_photographer_photos, incremental_photos, changed

        changed = photographer_has_drive_changes(changes_state, changes_cache)
        if folder_id is not None and not changed and contains_okand(old_photographer_photos):
            changed = True
            log_detail(f"Omgenererar {photographer_key} eftersom cachen innehåller okand.")
        if not changed:
            if has_drive_entries:
                update_photographer_change_cache(connection, photographer_key, changes_state)
            else:
                update_photographer_change_cache(
                    connection,
                    photographer_key,
                    changes_state,
                    old_drive_entries,
                )
            return old_photographer_photos, old_photographer_photos, False

    photographer_photos: dict[str, Any] = {}
    drive_entries: list[dict[str, Any]] = []

    if folder_id is None:
        assert file_id is not None
        add_drive_file(
            photographer_photos,
            photographer_key,
            file_id,
            drive_entries,
            fallback_name=drive_file_fallback_name(photographer_key, photographer),
        )
        cache_root_id = file_id
    else:
        add_drive_folder(photographer_photos, photographer_key, folder_id, [], drive_entries)
        cache_root_id = folder_id

    count = count_photos(photographer_photos)
    if count_entries(photographer_photos) == 0 and old_photographer_photos:
        log_detail(f"Inga Drive-poster hittades för {photographer_key}. Återanvänder databascache.")
        photographer_photos = old_photographer_photos
        count = count_photos(photographer_photos)
    elif photographer_photos != old_photographer_photos:
        log_detail(f"Uppdaterade databascache för {photographer_key} med {count} bilder.")
        log_file_changes(old_photographer_photos, photographer_photos)
    else:
        log_detail(f"Inget nytt för {photographer_key}. Databascache lämnas oförändrad.")

    if OAUTH_TOKEN:
        try:
            changes_state = build_changes_state(cache_root_id, drive_entries)
        except RuntimeError as error:
            log_detail(f"Kunde inte uppdatera Drive change-state för {photographer_key}: {error}")

    cache_changed = photographer_photos != old_photographer_photos
    save_photographer_cache(connection, photographer_key, photographer_photos, changes_state, drive_entries)
    return old_photographer_photos, photographer_photos, cache_changed


def run_update() -> None:
    global OAUTH_TOKEN
    started = time.perf_counter()
    reset_drive_json_stats()

    log("Startar uppdatering.","%Y-%m-%d")
    if not acquire_update_lock():
        return

    log_step("Laddar OAuth-token.")
    OAUTH_TOKEN = load_oauth_token()
    if OAUTH_TOKEN:
        log_step("OAuth används för Drive API och ändringskontroll.")
    elif GOOGLE_DRIVE_API_KEY:
        log_step("Google Drive API används för katalogkontroll.")
    else:
        log_step("GOOGLE_DRIVE_API_KEY saknas. Faller tillbaka till HTML-läsning.")

    log_step(f"Läser {PHOTOGRAPHERS_FILE.name}.")
    photographers = read_json(PHOTOGRAPHERS_FILE, {})
    photographer_keys = list(photographers.keys())
    photographer_key_set = set(photographer_keys)
    changes_cache: dict[str, tuple[list[dict[str, Any]], str]] = {}

    with open_database() as database:
        migrate_legacy_photographer_files(database, photographer_key_set)
        backfill_photo_counts(database)
        write_database_documentation(database)

        photos: dict[str, Any] | None = None
        photos_changed = False
        if not PHOTOS_FILE.exists():
            photos = build_photos_from_database(database, photographer_keys)
            photos_changed = True

        for removed_tree in delete_removed_photographer_caches(database, photographer_key_set):
            if photos is None:
                photos = read_json(PHOTOS_FILE, {})
                if not photos:
                    photos = build_photos_from_database(database, photographer_keys)
            remove_tree(photos, removed_tree)
            photos_changed = True

        for photographer_key, photographer in photographers.items():
            old_photographer_photos, photographer_photos, cache_changed = update_photographer_cache(
                database,
                photographer_key,
                photographer,
                changes_cache,
            )
            if cache_changed:
                if photos is None:
                    photos = read_json(PHOTOS_FILE, {})
                    if not photos:
                        photos = build_photos_from_database(database, photographer_keys)
                remove_tree(photos, old_photographer_photos)
                merge_tree(photos, photographer_photos)
                photos_changed = True

        total = count_database_photos(database, photographer_keys)

    if photos_changed:
        assert photos is not None
        write_json(PHOTOS_FILE, photos)
        log_step(f"Skapade {PHOTOS_FILE.name} med {total} bilder.")
    else:
        log_step(f"Inget nytt för {PHOTOS_FILE.name}. Databasen innehåller {total} bilder.")

    log_drive_json_stats()
    duration = time.perf_counter() - started
    log(f"Uppdatering klar. {duration:.3f} sekunder", "%Y-%m-%d")

    commit_and_push_updates()
    return


def main() -> int:
    start_log_section()
    try:
        run_update()
        return 0
    except KeyboardInterrupt as error:
        log(f"UPPDATERING AVBRUTEN: {type(error).__name__}")
        log_traceback(error)
        return 130
    except BaseException as error:
        log(f"UPPDATERING MISSLYCKADES: {type(error).__name__}: {error}")
        log_traceback(error)
        return 1
    finally:
        release_update_lock()


if __name__ == "__main__":
    sys.exit(main())
