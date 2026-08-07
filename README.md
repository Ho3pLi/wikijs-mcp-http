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
| `WIKIJS_API_KEY` | required | Wiki.js API key. Kept server-side and never returned by tools |
| `WIKIJS_GRAPHQL_ENDPOINT` | `/graphql` | Wiki.js GraphQL endpoint path |
| `WIKIJS_READ_ONLY` | `false` | When `true`, mutation tools are disabled |

Streamable HTTP configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_HOST` | `127.0.0.1` | Host interface for HTTP mode |
| `MCP_PORT` | `8000` | Port for HTTP mode |
| `MCP_PATH` | `/mcp` | MCP Streamable HTTP endpoint path |

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
