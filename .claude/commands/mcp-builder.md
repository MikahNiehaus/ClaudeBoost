---
description: Guide for building a high-quality MCP server in TypeScript or Python that integrates external APIs
argument-hint: "<service-name>"
allowed-tools: Read, Write, Bash, Glob, Grep, WebFetch, WebSearch
---

# /mcp-builder

Build a high-quality MCP (Model Context Protocol) server that enables LLMs to interact with external services through well-designed tools. The quality of an MCP server is measured by how well it enables agents to accomplish real-world tasks.

Target: **$ARGUMENTS** (e.g. `GitHub API`, `Stripe billing`, `internal database`)

---

## Phase 1: Research and Planning

### 1.1 Study the MCP Protocol

Start with the sitemap to find relevant spec pages:
```
WebFetch: https://modelcontextprotocol.io/sitemap.xml
```

Then fetch key pages with `.md` suffix for markdown format (e.g. `https://modelcontextprotocol.io/specification/draft.md`).

Key areas to review:
- Transport mechanisms (streamable HTTP vs stdio)
- Tool, resource, and prompt definitions
- Authentication and security patterns

### 1.2 Load SDK Documentation

**Recommended stack: TypeScript** (best SDK support, broad LLM training coverage, static typing)

```
# TypeScript SDK
WebFetch: https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md

# Python SDK (if Python is required)
WebFetch: https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md
```

### 1.3 Understand the Target API

Use WebSearch and WebFetch to review the target service's API documentation:
- Authentication mechanism (API key, OAuth, JWT)
- Key endpoints and data models
- Rate limits and pagination patterns
- Error response formats

### 1.4 Design Tool Coverage

**API Coverage vs. Workflow Tools**: Prioritize comprehensive API coverage. Workflow tools (combining multiple operations) are convenient but reduce agent flexibility. When uncertain, implement individual endpoint tools first.

List endpoints to implement, starting with the most commonly used operations. Aim to cover 100% of CRUD operations for primary resources.

**Tool naming**: Use consistent `service_verb_resource` patterns (e.g. `github_create_issue`, `github_list_repos`). Action-oriented, discoverable names.

---

## Phase 2: Implementation

### 2.1 Project Structure

**TypeScript project:**
```
my-mcp-server/
├── src/
│   ├── index.ts          # Server entry point
│   ├── client.ts         # API client and auth
│   ├── tools/            # One file per resource group
│   │   ├── issues.ts
│   │   └── repos.ts
│   └── utils.ts          # Shared helpers
├── package.json
├── tsconfig.json
└── README.md
```

**Python project:**
```
my-mcp-server/
├── server.py             # FastMCP entry point
├── client.py             # API client and auth
├── tools/                # One module per resource group
│   ├── issues.py
│   └── repos.py
└── pyproject.toml
```

### 2.2 Transport Selection

- **stdio**: Local servers (Claude Code, desktop clients). Simple, no network required.
- **Streamable HTTP (stateless JSON)**: Remote servers. Easier to scale; no session state.

For ClaudeBoost integration, prefer stdio for local tooling. Use the registration pattern from `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "my-server": {
      "command": "node",
      "args": ["dist/index.js"],
      "cwd": "/path/to/server"
    }
  }
}
```

### 2.3 Core Infrastructure

Build shared utilities first:
- API client with authentication headers
- Error handling that produces actionable messages (tell agents what to do next, not just what went wrong)
- Pagination helper (cursor-based or offset)
- Response formatter (return focused, relevant data — not raw API dumps)

### 2.4 Implement Each Tool

For every tool, define:

**Input schema** — use Zod (TypeScript) or Pydantic (Python):
- Mark required vs optional fields
- Add constraints (min/max, enum values, regex patterns)
- Include examples in field descriptions

**Output schema** — use `outputSchema` and `structuredContent` where supported:
- Helps clients understand and display results
- Return both text content and structured data

**Tool description** — concise, specific, tells agents when to use it:
- What it does
- Key parameters
- What it returns

**Annotations** (TypeScript SDK):
```typescript
{
  readOnlyHint: true,       // Does not modify state
  destructiveHint: false,   // Cannot be undone
  idempotentHint: true,     // Safe to retry
  openWorldHint: false      // Closed, deterministic results
}
```

**Error handling**: Errors must guide agents toward solutions:
```
"Authentication failed. Check that your API_KEY environment variable is set and has not expired."
```
Not:
```
"401 Unauthorized"
```

### 2.5 Security Requirements

- Never log secrets, tokens, or credentials (even in error messages)
- Read API keys from environment variables only — never hardcode
- Validate and sanitize all inputs before using in API calls
- Respect rate limits; implement exponential backoff on 429 responses
- Use HTTPS for all external API calls

---

## Phase 3: Test and Review

### 3.1 Build Verification

```bash
# TypeScript
npm run build

# Python
python -m py_compile server.py
```

### 3.2 Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Connect your server and verify:
- All tools appear in the tool list with correct descriptions
- Input schemas validate correctly
- Successful calls return expected structure
- Error cases return actionable messages

### 3.3 Code Quality Review

- No duplicated code (shared utilities for repeated patterns)
- Consistent error handling across all tools
- Full type coverage (no `any` in TypeScript, no untyped functions in Python)
- Tool descriptions are clear and unambiguous

---

## Phase 4: Evaluations

Create 10 evaluation questions to verify your server enables effective LLM use. Each question must be:
- **Independent**: Does not depend on other questions' results
- **Read-only**: Requires only non-destructive operations
- **Complex**: Requires multiple tool calls and exploration
- **Realistic**: Based on real use cases
- **Verifiable**: Single, clear, stable answer

Save evaluations as `evals.xml`:

```xml
<evaluation>
  <qa_pair>
    <question>How many open issues in the repository are labeled "bug" and were created in the last 30 days?</question>
    <answer>7</answer>
  </qa_pair>
  <!-- 9 more pairs -->
</evaluation>
```

---

## ClaudeBoost Registration

Once built and tested, register your new MCP server so all ClaudeBoost sessions can use it. Run `/update-config` and add the server entry to `~/.claude/settings.json` under `mcpServers`.

If the server is project-specific, add it to the project's `.claude/settings.json` instead.
