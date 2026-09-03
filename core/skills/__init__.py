"""Skill registry for NARA.

Skills are things NARA can *do* (vault, dev, macOS, web, content). ``skill_specs``
lists them with the commands that invoke them, for ``nara skills`` and, later, for
the orchestrator to expose them as callable tools.
"""
from __future__ import annotations


def skill_specs() -> list[dict]:
    return [
        {
            "name": "dev",
            "summary": "Delegate a coding task to Claude Code in a project repo.",
            "commands": ['nara dev <project> "<task>"'],
        },
        {
            "name": "macos",
            "summary": "Control macOS: open apps, run Shortcuts, set Focus.",
            "commands": ["nara macos open <App>", "nara macos shortcut <Name>"],
        },
        {
            "name": "web",
            "summary": "Search or fetch the web and save a summary to your vault.",
            "commands": ['nara web search "<query>"', "nara web url <url>"],
        },
        {
            "name": "content",
            "summary": "Draft marketing content from your vault (bilingual EN/ID).",
            "commands": ['nara draft "<topic>" [--kind caption|listing|outreach] [--bilingual]'],
        },
    ]
