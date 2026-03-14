"""GitHub tool registry with scope-based gating."""

from __future__ import annotations

GITHUB_TOOL_REGISTRY: list[dict[str, object]] = [
    {
        "key": "create_issue",
        "label": "Create issue",
        "description": "Create a new issue in a GitHub repository.",
        "required_scopes": ["repo"],
        "parameter_hints": "repository, title, body",
    },
    {
        "key": "add_issue_comment",
        "label": "Add issue comment",
        "description": "Add a comment to an existing GitHub issue.",
        "required_scopes": ["repo"],
        "parameter_hints": "repository, issue_number, body",
    },
    {
        "key": "list_issues",
        "label": "List issues",
        "description": "List open issues in a GitHub repository.",
        "required_scopes": ["repo"],
        "parameter_hints": "repository, state (open/closed/all)",
    },
    {
        "key": "create_pull_request",
        "label": "Create pull request",
        "description": "Create a new pull request.",
        "required_scopes": ["repo"],
        "parameter_hints": "repository, title, body, head, base",
    },
    {
        "key": "add_label",
        "label": "Add label",
        "description": "Add labels to an issue or pull request.",
        "required_scopes": ["repo"],
        "parameter_hints": "repository, issue_number, labels",
    },
]


def tools_for_scopes(scopes: list[str]) -> list[dict[str, object]]:
    scope_set = set(scopes)
    return [
        tool
        for tool in GITHUB_TOOL_REGISTRY
        if set(tool["required_scopes"]).issubset(scope_set)  # type: ignore[arg-type]
    ]
