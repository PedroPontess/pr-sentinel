import operator
import os
from typing import Annotated, TypedDict

from github import Auth, Github


class ReviewState(TypedDict):
    pr_url: str
    pr_diff: str
    changed_files: list[str]
    tool_calls_made: Annotated[list[str], operator.add]
    findings: Annotated[list[str], operator.add]
    iterations: int
    next_action: str
    done: bool


def fetch_context(state: ReviewState) -> str:
    gh = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))

    parts = state["pr_url"].rstrip("/").split("/")
    owner_repo = f"{parts[-4]}/{parts[-3]}"
    pr_number = int(parts[-1])

    repo = gh.get_repo(owner_repo)
    pr = repo.get_pull(pr_number)

    diff_text = ""
    changed_files = []
    for file in pr.get_files():
        changed_files.append(file.filename)
        if file.patch:
            diff_text += f"--- {file.filename} ---\n{file.patch}\n\n"

    return {
        "pr_diff": diff_text,
        "changed_files": changed_files,
        "iterations": 0,
        "done": False,
    }


def decide_next_tool(state: ReviewState, config: dict) -> dict:
    prompt = f"""You are reviewing a PR. Diff:\n{state["pr_diff"]}\n\n
Tools already used: {state["tool_calls_made"]}\n
Findings so far: {state["findings"]}\n\n
Decide ONE next action: 'run_static_analysis', 'check_tests', 'read_full_file', or 'finish'.
Respond with only the action name."""

    llm = config["configurable"]["llm"]
    decision = llm.invoke(prompt).content.strip()
    return {
        "iterations": state["iterations"] + 1,
        "next_action": decision,
    }
