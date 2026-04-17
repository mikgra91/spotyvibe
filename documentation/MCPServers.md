# Optional MCP Servers (per-developer)

MCP server configs live in each developer's `settings.local.json` (not committed).
Below are recommended servers for this project.

## Spotify MCP (`marcelmarais/spotify-mcp-server`)

Provides 30+ Spotify Web API tools (search, playlist CRUD, playback, queue, devices). Useful for live API exploration, verifying response shapes after API changes, and testing search queries without running the app.

**Setup:**
```bash
cd ~/.claude/mcp-servers
git clone https://github.com/marcelmarais/spotify-mcp-server.git
cd spotify-mcp-server
npm install && npm run build
```
Then create a Spotify app at https://developer.spotify.com/dashboard with redirect URI `http://127.0.0.1:8888/callback`, and run `npm run auth` to complete OAuth. Add to your `settings.local.json`:
```json
{
  "mcpServers": {
    "spotify": {
      "command": "node",
      "args": ["<HOME>/.claude/mcp-servers/spotify-mcp-server/build/index.js"]
    }
  }
}
```

**When to use:** Verify Spotify API behavior, test search queries, inspect playlist structures, debug field names after API changes. Consult `SKILL.md` alongside MCP results for known breaking changes.

## GitHub MCP (`github/github-mcp-server`)

Official GitHub MCP server. Monitor CI/CD workflow runs (`release.yml`, `beta.yml`), inspect check failures, review PRs, and manage issues directly from Claude.

**Setup (requires Docker or Podman):**
```json
{
  "mcpServers": {
    "github": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_PAT>"
      }
    }
  }
}
```
Create a PAT at https://github.com/settings/personal-access-tokens/new with `repo` and `read:org` scopes. Substitute `docker` for `podman` if using Docker Desktop. On Windows, use the full path to the Podman executable if it's not in PATH.

**When to use:** Monitor CI/CD builds, review PRs, trace test failures to commits, manage issues.

## Playwright MCP (`microsoft/playwright-mcp`)

Browser automation via accessibility snapshots (not screenshots). Run Playwright tests, debug frontend behavior, and verify UI changes in a real browser.

**Setup (no build needed):**
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

**When to use:** Test UI changes in a live browser, debug DOM/accessibility issues, verify responsive layout behavior.

## MDN MCP (`mdn/mcp`)

Live MDN Web Docs access — current CSS, JavaScript, and Web API references with browser compatibility data. No stale knowledge cutoff.

**Setup (remote, no install):**
```json
{
  "mcpServers": {
    "mdn": {
      "type": "url",
      "url": "https://mcp.mdn.mozilla.net/sse"
    }
  }
}
```

**When to use:** Look up vanilla JS APIs, CSS properties, browser compatibility. Especially useful for this project's no-framework, no-bundler frontend stack.
