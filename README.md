# Lavalink Pulse — GitHub Pages Status Dashboard

A dependency-free, responsive monitoring dashboard for a Lavalink node. The website itself is static and can be hosted on GitHub Pages; a GitHub Actions workflow polls Lavalink from a runner, then publishes sanitized status/history JSON for the dashboard to read.

## Features

- Online/offline/setup state, last checked timestamp, stale-data warning, and endpoint copy button
- API response latency chart with 1 hour, 24 hour, 7 day, and 30 day windows
- Calculated availability, successful/failed checks, average latency, and peak latency
- Lavalink player counts, process uptime, JVM memory, CPU/system load, and reported Lavalink version
- Recent-check table, outage/recovery timeline, and export to CSV/JSON
- Manual dashboard refresh, optional 60-second browser auto-refresh, and light/dark theme
- No JavaScript packages, build step, server, or GitHub Actions secrets required
- Status history retained for approximately 30 days at the default five-minute polling interval

## Deploy to GitHub Pages

1. Create a new GitHub repository and upload the contents of this folder (keep `.github/`, `data/`, and `monitor.py`).
2. No GitHub Actions secrets are required. The password is configured directly in `monitor.py`.
3. The host, port, and protocol defaults are already set to the node from your request. You can override them using repository **Variables** named `LAVALINK_HOST`, `LAVALINK_PORT`, and `LAVALINK_SECURE` (`true` for HTTPS, `false` for HTTP).
4. Open **Actions → Monitor Lavalink → Run workflow** once. The first successful run writes `data/status.json` and `data/history.json`.
5. In **Settings → Pages**, set the source to **Deploy from a branch**, choose your default branch (usually `main`) and the `/(root)` folder. Save.
6. Open the Pages URL shown in Settings → Pages. The dashboard loads the JSON snapshots from `data/`.

The workflow is scheduled for every five minutes. GitHub Actions scheduled runs can be delayed, especially during periods of high GitHub load, so checks are approximate rather than guaranteed to happen exactly on schedule. If you use a private repository, verify that your GitHub plan permits the Pages visibility you want.

## Security notes

- **No secrets are used in this version.** The password is stored as a plain-text constant in `monitor.py` so the workflow works without GitHub Actions secrets.
- **Security trade-off:** if this repository is public, anyone can read `monitor.py` and obtain the password. Since `youshallnotpass` is a widely known example password and was shared in this conversation, change it in both `monitor.py` and your Lavalink node configuration before deploying if you administer the node. This no-secrets version is not suitable for a public repository with a real credential.
- The monitor publishes server status, version, latency, player counts, memory/CPU statistics, and failure messages to `data/`. Treat these as public information because the Pages website is public.
- Because your current protocol is HTTP (`secure: false`), requests from the GitHub Actions runner are unencrypted in transit. If your provider supports TLS/HTTPS, enable it and set `LAVALINK_SECURE` to `true`.
- The password is not sent to browser JavaScript or written to status snapshots. GitHub Pages is static hosting, so any credential committed to a public repository is still publicly readable.

## Troubleshooting

- **HTTP 401**: confirm the password in `monitor.py` matches the node configuration.
- **HTTP 401**: confirm the password in `monitor.py` matches the password configured in Lavalink. Rotate it if exposed.
- **HTTP 404**: the monitor tries Lavalink v4 and falls back to v3 stats if `/v4/stats` returns 404. If the node uses a custom API/proxy path, adapt `monitor.py` accordingly.
- **Connection failed / timeout**: check that the node is reachable from outside its host machine and that the port is exposed. Some hosting providers may block requests from GitHub Actions runner IP ranges.
- **Dashboard keeps saying pending**: confirm Actions completed, `data/status.json` was committed, Pages is serving the repository root, and the page URL is not serving a cached copy.
- **History not updating**: the workflow needs `contents: write` permission. Check repository Actions settings and branch protection rules that may reject the bot's commit.

## Local preview

Open `index.html` directly only for visual preview; browsers generally block `fetch()` from local files. For a full local preview from the project folder, run:

```bash
python -m http.server 8080
```

Then open `http://localhost:8080`.

## Data contract

- `data/status.json`: latest result, public node details, version, and latest REST stats.
- `data/history.json`: chronological status samples used for charts, availability, incidents, and exports.

The frontend is intentionally read-only. It does not expose Lavalink player-control endpoints or let visitors control the audio node.
