# AGENTS.md — non-Claude AI coding agents

This file exists for non-Claude agents (Codex, Cursor, etc.). **Claude users: read [`CLAUDE.md`](CLAUDE.md) instead — everything is there.**

## 🔴 Absolute git rule

NEVER run `git commit`, `git push`, or any command that creates commits or pushes to a remote, unless the user's **current message** contains the **exact case-sensitive string `CP ALLOWED`** as a standalone instruction. No natural-language equivalent grants permission. One `CP ALLOWED` = one git operation; permission revokes the instant it completes.

## Project pointers

- [`CLAUDE.md`](CLAUDE.md) — full rules: build/run, where-to-change-what, context discipline, project North Star (Quality > Price > Speed)
- [`documentation/api/spotify.md`](documentation/api/spotify.md) — Spotify Web API reference + conventions
- [`documentation/conventions.md`](documentation/conventions.md) — accessibility + i18n
- [`documentation/MCPServers.md`](documentation/MCPServers.md) — optional MCP servers
- [`documentation/TechnicalManual.md`](documentation/TechnicalManual.md) — architecture, modules, data flow, test recipes
