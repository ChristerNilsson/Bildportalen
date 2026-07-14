from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = REPO_ROOT / "2026.log"

def fib(n: int) -> int:
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    elif n > 1:
        return fib(n - 1) + fib(n - 2)
    else: return n


# print(fib(30))


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def main() -> None:
    started = time.perf_counter()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    run_git("add", "2026.log")
    z = fib(31)

    duration = time.perf_counter() - started
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"{timestamp} duration={duration:.3f}s {z}\n")

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
