from datetime import datetime, timezone
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = REPO_ROOT / "2026.log"


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def main() -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"{timestamp}\n")

    run_git("add", "2026.log")

    diff = run_git("diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        print("No log changes to commit")
        return

    if diff.returncode != 1:
        raise subprocess.CalledProcessError(
            diff.returncode,
            diff.args,
            output=diff.stdout,
            stderr=diff.stderr,
        )

    run_git("commit", "-m", "Log timestamp")
    run_git("push")


if __name__ == "__main__":
    main()
