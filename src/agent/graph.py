import operator
import os
from typing import Annotated, TypedDict

from github import Auth, Github, GithubException
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from tools import run_static_analysis


class ReviewState(TypedDict):
    pr_url: str
    pr_diff: str
    changed_files: list[str]
    pr_head_sha: str
    tool_calls_made: Annotated[list[str], operator.add]
    files_analyzed: Annotated[list[str], operator.add]
    findings: Annotated[list[dict], operator.add]
    iterations: int
    next_action: str
    done: bool


def fetch_context(state: ReviewState) -> dict:
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
        "pr_head_sha": pr.head.sha,
        "files_analyzed": [],
        "iterations": 0,
        "done": False,
    }


def fetch_file_content(state: ReviewState, filepath: str) -> str | None:
    gh = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
    parts = state["pr_url"].rstrip("/").split("/")
    owner_repo = f"{parts[-4]}/{parts[-3]}"
    repo = gh.get_repo(owner_repo)

    try:
        content_file = repo.get_contents(filepath, ref=state["pr_head_sha"])
        return content_file.decoded_content.decode("utf-8")
    except (GithubException, UnicodeDecodeError) as e:
        print(f"[fetch_file_content] could not fetch {filepath}: {e}")
        return None


def decide_next_tool(state: ReviewState, config: RunnableConfig) -> dict:
    prompt = f"""You are reviewing a PR. Diff:\n{state["pr_diff"]}\n\n
Tools already used: {state["tool_calls_made"]}\n
Findings so far: {state["findings"]}\n\n
Decide ONE next action: 'run_static_analysis', 'check_tests', 'read_full_file', or 'finish'.
Respond with only the action name."""

    llm = config["configurable"]["llm"]
    valid_actions = {"run_static_analysis", "check_tests", "read_full_file", "finish"}

    decision = llm.invoke(prompt).content.strip().lower()
    if decision not in valid_actions:
        decision = "finish"
    return {
        "iterations": state["iterations"] + 1,
        "next_action": decision,
    }


def _next_unanalyzed_file(
    state: ReviewState, tool_name: str, extensions: tuple[str, ...]
) -> str | None:
    candidates = [f for f in state["changed_files"] if f.endswith(extensions)]
    prefix = f"{tool_name}"
    already_done = {
        entry.removeprefix(prefix)
        for entry in state["files_analyzed"]
        if entry.startswith(f"{tool_name}:")
    }
    remaining = [f for f in candidates if f not in already_done]
    return remaining[0] if remaining else None


def call_tool(state: ReviewState) -> dict:
    action = state["next_action"]

    if action == "finish":
        return {"done": True}

    if action == "run_static_analysis":
        target_path = _next_unanalyzed_file(state, "run_static_analysis", (".py"))
        if target_path is None:
            result = "All Python files already checked with static analysis."
            files_analyzed_update = []
        else:
            content = fetch_file_content(state, target_path)
            if content is not None:
                result = run_static_analysis(content)
            else:
                result = f"Could not fetch {target_path} for analysis."
            files_analyzed_update = [f"run_static_analysis:{target_path}"]
        return {
            "tool_calls_made": [action],
            "files_analyzed": files_analyzed_update,
            "findings": [{"tool": action, "result": result}],
        }

    if action == "check_tests":
        return {
            "tool_calls_made": [action],
            "findings": [{"tool": action, "result": "Test check not implemented."}],
        }

    if action == "read_full_file":
        return {
            "tool_calls_made": [action],
            "findings": [
                {"tool": action, "result": "read_full_file not yet implemented"}
            ],
        }

    return {"done": True}


def check_if_done(state: ReviewState) -> str:
    if state["done"] or state["iterations"] >= 5:
        return "generate_review"
    return "decide_next_tool"


def generate_review(state: ReviewState, config: RunnableConfig) -> dict:
    prompt = f"Summarize these findings into a structured review with severity tags:\n{state['findings']}"
    llm = config["configurable"]["llm"]
    final = llm.invoke(prompt)
    return {"findings": [{"summary": final.content}]}


def build_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("fetch_context", fetch_context)
    graph.add_node("decide_next_tool", decide_next_tool)
    graph.add_node("call_tool", call_tool)
    graph.add_node("generate_review", generate_review)

    graph.set_entry_point("fetch_context")
    graph.add_edge("fetch_context", "decide_next_tool")
    graph.add_edge("decide_next_tool", "call_tool")
    graph.add_conditional_edges(
        "call_tool",
        check_if_done,
        {
            "decide_next_tool": "decide_next_tool",
            "generate_review": "generate_review",
        },
    )
    graph.add_edge("generate_review", END)

    return graph.compile()
