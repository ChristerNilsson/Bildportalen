from datetime import datetime, timezone
from pathlib import Path


LOG_FILE = Path("2026.log")


def main() -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"{timestamp}\n")


if __name__ == "__main__":
    main()
