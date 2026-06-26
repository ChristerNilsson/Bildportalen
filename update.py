from __future__ import annotations

import html
import json
import os
import re
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
PHOTOGRAPHERS_FILE = ROOT / "photographers.json"
PHOTOS_FILE = ROOT / "photos.json"
LOG_FILE = ROOT / "update.log"
PHOTOGRAPHER_DATA_DIR = ROOT / "photographers"
OAUTH_CREDENTIALS_FILE = ROOT / "credentials.json"
OAUTH_TOKEN_FILE = ROOT / "token.json"
OAUTH_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
BUILTIN_TOP_LEVEL_LINKS = {
    "Help.pdf": "1-MZngZMde5PSEWFVY147ZBytqze9iGkd",
}
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


def main() -> None:
    global OAUTH_TOKEN
    start_log_section()
    log("Startar uppdatering.")
    OAUTH_TOKEN = load_oauth_token()
    if OAUTH_TOKEN:
        log_step("OAuth används för Drive API och ändringskontroll.")
    elif GOOGLE_DRIVE_API_KEY:
        log_step("Google Drive API används för katalogkontroll.")
    else:
        log_step("GOOGLE_DRIVE_API_KEY saknas. Faller tillbaka till HTML-läsning.")

    photographers = read_json(PHOTOGRAPHERS_FILE, {})
    photos: dict[str, Any] = {}
    total = 0

    for photographer_key, photographer in photographers.items():
        if not isinstance(photographer, list) or len(photographer) < 2:
            log(f"Hoppar över {photographer_key}: fotografposten saknar Drive-url.")
            continue

        folder_id = drive_id_from_url(photographer[1])
        if folder_id is None:
            log(f"Hoppar över {photographer_key}: kan inte läsa Drive-id ur {photographer[1]!r}.")
            continue

        log_step(f"Hämtar {photographer_key}.")
        photographer_file = PHOTOGRAPHER_DATA_DIR / f"{photographer_key}.json"
        changes_file = PHOTOGRAPHER_DATA_DIR / f"{photographer_key}.changes.json"
        old_photographer_photos = read_json_with_legacy(photographer_file, ROOT / photographer_file.name, {})
        changes_state = read_json_with_legacy(changes_file, ROOT / changes_file.name, {})

        if OAUTH_TOKEN and old_photographer_photos and changes_state:
            changed = photographer_has_drive_changes(changes_state)
            if not changed and contains_okand(old_photographer_photos):
                changed = True
                log_detail(f"Omgenererar {photographer_file.name} eftersom den innehåller okand.")
            if not changed:
                log_detail(f"Inga Drive-ändringar för {photographer_key}. {photographer_file.name} lämnas oförändrad.")
                ensure_json_file(photographer_file, old_photographer_photos)
                write_json(changes_file, changes_state)
                total += count_photos(old_photographer_photos)
                merge_tree(photos, old_photographer_photos)
                continue

        photographer_photos: dict[str, Any] = {}
        drive_entries: list[dict[str, Any]] = []

        add_drive_folder(photographer_photos, photographer_key, folder_id, [], drive_entries)
        count = count_photos(photographer_photos)

        if count_entries(photographer_photos) == 0 and old_photographer_photos:
            log_detail(f"Inga Drive-poster hittades för {photographer_key}. Återanvänder {photographer_file.name}.")
            photographer_photos = old_photographer_photos
            count = count_photos(photographer_photos)
        elif photographer_photos != old_photographer_photos:
            write_json(photographer_file, photographer_photos)
            log_detail(f"Skapade {photographer_file.name} med {count} bilder.")
        else:
            log_detail(f"Inget nytt för {photographer_key}. {photographer_file.name} lämnas oförändrad.")

        if OAUTH_TOKEN:
            try:
                write_json(changes_file, build_changes_state(folder_id, drive_entries))
            except RuntimeError as error:
                log_detail(f"Kunde inte skapa {changes_file.name}: {error}")

        total += count
        merge_tree(photos, photographer_photos)

    ensure_builtin_top_level_links(photos)
    write_json(PHOTOS_FILE, photos)
    log_step(f"Skapade {PHOTOS_FILE.name} med {total} bilder.")
    log("Uppdatering klar.")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_json_with_legacy(path: Path, legacy_path: Path, default: Any) -> Any:
    if path.exists():
        return read_json(path, default)
    return read_json(legacy_path, default)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_json_file(path: Path, data: Any) -> None:
    if data and not path.exists():
        write_json(path, data)
        log(f"Skapade {path.name}.")


def ensure_builtin_top_level_links(photos: dict[str, Any]) -> None:
    for name, target in BUILTIN_TOP_LEVEL_LINKS.items():
        photos[name] = target


def log(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"{timestamp} {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def log_step(message: str) -> None:
    log(f" {message}")


def log_detail(message: str) -> None:
    log(f"  {message}")


def start_log_section() -> None:
    print()
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write("\n")


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
    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return query_id[0]
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", url):
        return url
    return None


def photographer_has_drive_changes(changes_state: dict[str, Any]) -> bool:
    if changes_state.get("schemaVersion") != OUTPUT_SCHEMA_VERSION:
        return True

    page_token = changes_state.get("pageToken", "")
    if not page_token:
        return True

    tracked_ids = set(changes_state.get("trackedIds", []))
    if not tracked_ids:
        return True

    try:
        changes, new_page_token = list_drive_changes(page_token)
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
            "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,parents,trashed))",
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
                taken_time = timestamp_seconds_since_1900(image_time) or timestamp_seconds_since_1900(modified_time)
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
            return json.loads(response.read().decode("utf-8"))
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


if __name__ == "__main__":
    main()
