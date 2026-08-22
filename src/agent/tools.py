import os
import subprocess
import tempfile


def run_static_analysis(file_content: str, display_name: str | None = None) -> str:
    """Runs ruff on a Python file and returns the findings as text."""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["ruff", "check", tmp_path],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout or "No issues found."
        if display_name:
            output = output.replace(tmp_path, display_name)
        return output
    finally:
        os.remove(tmp_path)
