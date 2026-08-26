# WikiJS MCP Server

An MCP server that connects MCP clients to your [Wiki.js](https://js.wiki/) instance. It can run locally over stdio or remotely over the official MCP Streamable HTTP transport.

## Prerequisites

- Python 3.10+
- A Wiki.js instance with API access enabled
- A Wiki.js API key (Administration > API Access > New API Key)

## Installation

```bash
pip install wikijs-mcp
```

For local development:

```bash
git clone https://github.com/Ho3pLi/wikijs-mcp-http.git
cd wikijs-mcp-http
pip install -e .
```

## Configuration

Wiki.js configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `WIKIJS_URL` | required | Base URL of your Wiki.js instance |
| `WIKIJS_API_KEY` | required for stdio/single-key mode | Legacy/default Wiki.js API key. Kept server-side and never returned by tools |
| `WIKIJS_GRAPHQL_ENDPOINT` | `/graphql` | Wiki.js GraphQL endpoint path |
| `WIKIJS_READ_ONLY` | `false` | When `true`, mutation tools are disabled |

Streamable HTTP configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_HOST` | `127.0.0.1` | Host interface for HTTP mode |
| `MCP_PORT` | `8000` | Port for HTTP mode |
| `MCP_PATH` | `/mcp` | MCP Streamable HTTP endpoint path |
| `MCP_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*` | Comma-separated Host header allowlist |
| `MCP_ALLOWED_ORIGINS` | `http://127.0.0.1:*,http://localhost:*` | Comma-separated Origin header allowlist |

Cloudflare Access multi-user authorization, for remote Streamable HTTP deployments:

| Variable | Default | Description |
|----------|---------|-------------|
| `WIKIJS_CF_ACCESS_ISSUER` | unset | Cloudflare Access JWT issuer, usually `https://<team-name>.cloudflareaccess.com` |
| `WIKIJS_CF_ACCESS_AUDIENCE` | unset | Cloudflare Access application audience tag |
| `WIKIJS_CF_ACCESS_JWKS_URL` | unset | Cloudflare Access JWKS URL, usually `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs` |
| `WIKIJS_AUTH_USERS` | unset | User email to credential profile mapping |
| `WIKIJS_AUTH_PROFILES` | unset | Credential profile to Wiki.js API-key environment variable mapping |

The server does not bind to `0.0.0.0` by default. For production, put HTTPS/authentication in front of the local HTTP listener.

## Running

### Local / stdio

`stdio` is the default transport:

```bash
WIKIJS_URL=https://wiki.example.com \
WIKIJS_API_KEY=... \
wikijs-mcp
```

Equivalent explicit form:

```bash
WIKIJS_URL=https://wiki.example.com \
WIKIJS_API_KEY=... \
wikijs-mcp --transport stdio
```

### Remote / Streamable HTTP

```bash
WIKIJS_URL=https://wiki.example.com \
WIKIJS_API_KEY=... \
MCP_HOST=127.0.0.1 \
MCP_PORT=8000 \
MCP_PATH=/mcp \
wikijs-mcp --transport streamable-http
```

This exposes a standards-compliant MCP endpoint at:

```text
http://127.0.0.1:8000/mcp
```

The endpoint is intended to be proxied by HTTPS infrastructure later. Do not commit credentials or expose the Wiki.js API key to clients.

When deploying behind a reverse proxy with a public hostname, explicitly allow that hostname and its browser origin:

```text
MCP_HOST=127.0.0.1
MCP_PORT=8000
MCP_PATH=/mcp
MCP_ALLOWED_HOSTS=127.0.0.1:*,localhost:*,mcp.example.com
MCP_ALLOWED_ORIGINS=http://127.0.0.1:*,http://localhost:*,https://mcp.example.com
```

The MCP Python SDK enforces DNS rebinding protection for HTTP transports. Keep that protection enabled. Do not use `*`, disable DNS rebinding protection, or spoof the `Host` header in nginx merely to bypass validation.

### Cloudflare Access multi-user mode

By default, both stdio and Streamable HTTP use the single `WIKIJS_API_KEY`.

For a remote MCP protected by Cloudflare Access, you can enable multi-user mode. The server validates the `Cf-Access-Jwt-Assertion` header, extracts the authenticated email, maps it to a credential profile, then uses the Wiki.js API key from that profile only for the current MCP request. It does not mutate the global config or reuse a client with a changed authorization header.

Example:

```text
WIKIJS_URL=https://wiki.example.com
WIKIJS_CF_ACCESS_ISSUER=https://example.cloudflareaccess.com
WIKIJS_CF_ACCESS_AUDIENCE=0000000000000000000000000000000000000000000000000000000000000000
WIKIJS_CF_ACCESS_JWKS_URL=https://example.cloudflareaccess.com/cdn-cgi/access/certs

WIKIJS_AUTH_USERS=admin@example.com=admin,friend1@example.com=friends,friend2@example.com=friends
WIKIJS_AUTH_PROFILES=admin=WIKIJS_API_KEY_ADMIN,friends=WIKIJS_API_KEY_FRIENDS

WIKIJS_API_KEY_ADMIN=fake-admin-api-key
WIKIJS_API_KEY_FRIENDS=fake-friends-api-key
```

JSON object syntax is also accepted for the mappings:

```text
WIKIJS_AUTH_USERS={"admin@example.com":"admin","friend@example.com":"friends"}
WIKIJS_AUTH_PROFILES={"admin":"WIKIJS_API_KEY_ADMIN","friends":"WIKIJS_API_KEY_FRIENDS"}
```

Do not put Wiki.js API keys directly in `WIKIJS_AUTH_USERS` or `WIKIJS_AUTH_PROFILES`; profiles reference environment variable names only. Multiple users can share one profile, and the Wiki.js API key assigned to that profile should be associated with the corresponding Wiki.js group. Wiki.js remains the source of truth for page permissions and Page Rules.

When multi-user mode is configured in Streamable HTTP mode:

- Missing or invalid `Cf-Access-Jwt-Assertion` is rejected.
- Expired assertions, wrong issuer, and wrong audience are rejected.
- Authenticated users without a mapping are rejected.
- Missing profile definitions or missing API-key environment variables are rejected.
- The server does not fall back to `WIKIJS_API_KEY` for remote authenticated requests.

In stdio, local use remains unchanged and uses `WIKIJS_API_KEY`.

In Cloudflare, the Access application audience tag is visible in the Access application settings. The issuer and JWKS URL are based on your team domain:

```text
WIKIJS_CF_ACCESS_ISSUER=https://<team-name>.cloudflareaccess.com
WIKIJS_CF_ACCESS_JWKS_URL=https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs
```

To add a new Wiki.js group/API key:

1. Create or select the Wiki.js group and Page Rules in Wiki.js.
2. Create a Wiki.js API key associated with that group.
3. Store the key in a new environment variable, for example `WIKIJS_API_KEY_PARTNERS`.
4. Add a profile entry, for example `partners=WIKIJS_API_KEY_PARTNERS`.
5. Map one or more Cloudflare Access user emails to `partners`.

### Read-only mode

To allow reads while blocking writes:

```bash
WIKIJS_READ_ONLY=true wikijs-mcp --transport streamable-http
```

When enabled, these tools return an MCP-visible error before contacting Wiki.js:

- `wiki_create_page`
- `wiki_update_page`
- `wiki_move_page`
- `wiki_delete_page`

Read-only tools continue to work normally.

## MCP client examples

### Claude Code stdio

```bash
claude mcp add wikijs \
  --scope user \
  -e WIKIJS_URL=https://your-wiki.com \
  -e WIKIJS_API_KEY=your-api-key \
  -- pipx run wikijs-mcp
```

### Generic stdio config

```json
{
  "mcpServers": {
    "wikijs": {
      "command": "pipx",
      "args": ["run", "wikijs-mcp"],
      "env": {
        "WIKIJS_URL": "https://your-wiki.com",
        "WIKIJS_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `wiki_search` | Full-text search across all wiki pages |
| `wiki_get_page` | Get a page by path or ID, with optional `metadata_only` and `include_render` modes |
| `wiki_list_pages` | List pages with optional tag filtering and sort order |
| `wiki_get_tree` | Get the hierarchical folder/page tree structure |
| `wiki_create_page` | Create a new page |
| `wiki_update_page` | Update a page via full replacement or surgical find-and-replace (`edits`) |
| `wiki_move_page` | Move a page to a new path and/or locale |
| `wiki_delete_page` | Delete a page |
| `wiki_list_tags` | List all tags used across the wiki |
| `wiki_get_site_info` | Get wiki site metadata (title, description, host) |
| `wiki_get_history` | Get page edit history with pagination |
| `wiki_get_version` | Retrieve a specific historical version of a page |

## Development

```bash
pip install -e .
pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-xdist ruff
pytest
ruff check .
```

## License

MIT
