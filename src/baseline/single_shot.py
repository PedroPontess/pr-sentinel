import os

from dotenv import load_dotenv
from github import Auth, Github
from langchain_ollama import ChatOllama

load_dotenv()


def retrieve_pr(repo_name: str, pr_number: int) -> str:
    gh = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(1)  # Replace with the actual PR number

    diff_text = ""
    for file in pr.get_files():
        patch = file.patch or "No diff available"
        diff_text += f"--- {file.filename} ---\n{patch}\n\n"
    return diff_text


def one_shot_llm(diff_text: str) -> str:

    prompt = f"""You are an expert static analysis and code review engine. 
Review the following Git pull request diff with extreme technical precision.

Focus exclusively on finding:
1. Runtime exceptions and crashes (e.g., unhandled None/null access, invalid type operations, AttributeError, TypeError).
2. Framework-specific misuse (e.g., unsupported Django ORM queryset operations, incorrect slicing, invalid queries).
3. Import/Dependency errors (e.g., importing non-existent classes, functions, or modules).
4. Logic errors and edge cases where execution breaks on non-standard inputs (e.g., API key authentication, empty sets, non-numeric fields).

Rules:
- Do NOT generate generic advice, boilerplate test suggestions, style critiques, or theoretical security risks unless there is a clear, traceable exploit path.
- Trace every variable's type, nullability, and call-site assumptions carefully.
- For each genuine issue, provide:
  - File path and approximate location.
  - The exact exception or runtime failure that will occur.
  - A precise technical explanation of why the code fails.

Diff to review:
{diff_text}
"""

    llm = ChatOllama(model="qwen2.5-coder:7b", num_ctx=16384)
    response = llm.invoke(prompt)
    print(response.content)


if __name__ == "__main__":
    repo_name = "ai-code-review-evaluation/sentry-greptile"
    retrieved_diff = retrieve_pr(repo_name, pr_number=1)
    one_shot_llm(retrieved_diff)
