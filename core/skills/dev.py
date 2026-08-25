"""Dev skill — delegate coding tasks to Claude Code via the Claude Agent SDK.

Implemented in **Phase 3**. Will expose a ``DevSkill`` with:

    run_task(project, task, allow_bash=False)  -> summary + files changed + cost
    resume(task_id, followup)                  -> continue a previous session

Runs the agent with ``cwd`` set to the resolved repo, permission mode
``acceptEdits`` plus a least-privilege bash allowlist (never
``--dangerously-skip-permissions``), and enforces a ``max_cost_usd`` ceiling.
"""
