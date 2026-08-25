"""Skill registry for NARA.

Skills are tools the orchestrator can call — vault, dev (Claude Code), macOS
control, web. Each skill declares a JSON schema so the orchestrator can invoke
it as a tool. The auto-discovery registry arrives with Phase 2 (tool loop) and
grows in Phase 7 (skills & automations).
"""
