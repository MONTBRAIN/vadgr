# Vadgr Frontend

React dashboard for managing agents, running workflows, and viewing results. Cross-platform: works on Windows, macOS, and Linux.

## Requirements

- **Node.js >= 22** (LTS)
- **npm >= 10**

### Install Node.js

Use [nvm](https://github.com/nvm-sh/nvm) (recommended -- manages multiple Node versions, works on all platforms):

```bash
# Linux/macOS: install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash

# Windows: use nvm-windows from https://github.com/coreybutler/nvm-windows

# Then install and use Node 22
nvm install 22
nvm use 22
```

Or use the system package manager:

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# macOS (Homebrew)
brew install node@22

# Windows
# Download from https://nodejs.org/
```

## Setup

```bash
cd frontend
npm install
```

## Development

```bash
npm run dev
```

Opens at http://localhost:3000. Proxies `/api` to the backend at `http://127.0.0.1:8000`.

The backend must be running for the frontend to work. See [api/ README](../api/README.md).

## Build for production

```bash
npm run build
```

Outputs static files to `dist/`. Serve with any static file server (nginx, caddy, etc.).

## Tests

```bash
npm test           # Watch mode
npx vitest run     # Single run (CI)
```

23 unit tests covering types, API client, and UI components.

## Stack

| Dependency | Version | Purpose |
|---|---|---|
| React | 19.x | UI framework |
| TypeScript | 5.9.x | Type safety |
| Vite | 7.x | Build tool and dev server |
| Tailwind CSS | 4.x | Styling |
| TanStack Query | 5.x | Server state and caching |
| React Router | 7.x | Client-side routing |
| Vitest | 4.x | Unit testing |

## Pages

- **Dashboard** -- Overview with recent agents, runs, and stats
- **Agents** -- List, create, edit, delete agents
- **Agent Detail** -- View agent config, run with inputs, see schemas
- **Runs** -- List all runs with status filters
- **Run Viewer** -- Real-time execution output with metadata
- **Settings** -- Default provider, theme, auto-refresh (local storage)
