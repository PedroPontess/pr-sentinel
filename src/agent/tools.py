import subprocess


def run_static_analysis(filepath: str) -> str:
    """Runs ruff on a Python file and returns the findings as text."""
    result = subprocess.run(
        ["ruff", "check", filepath],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout or "No issues found."


if __name__ == "__main__":
    run_static_analysis()
