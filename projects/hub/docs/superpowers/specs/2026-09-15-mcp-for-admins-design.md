# The hub's MCP server answers admins only, over HTTP, with a token of their own

Date: 2026-09-15. Status: decided with Ivan the same day, being built in one PR.
Tracker: the REB card that names this file, in `Hub v0 - signups and the company flow,
deployed`. In English, per the repository rule; the product strings stay in Italian.

## 0. Why

The hub's MCP server (`apps/mcp`) was «an admin's tool by construction»: no credential,
because the only way to start it was on a machine that already held the database URL.
REB-206 added the CV's text to it, and Ivan asked the same day for the boundary the
docstring had been promising: «queste informazioni però sì via mcp ma solo agli utenti
segnati come admin», then «così come tutti i tool dell'mcp se sei admin (come
ivansala@humancraft.tech) su tutte le superfici (pannello amministrativo e pigro); se non
lo sei il tool mcp deve leggere solo dai dati del rispettivo database di pigro».

Asked how the two surfaces should relate, given that the hub and PigroCRM share nothing
but `shared/` and their public APIs, he chose **two servers, two tokens**: the hub's MCP
for the people in `admin_users`, with everything the admin area shows, the CRM's spaces
included; PigroCRM's MCP as it is, where a user already reads only their own space with a
personal token of that space. A person who is an admin here and a user there holds one
token for each.

## 1. The decisions, one paragraph each

**Credential.** A personal token per admin, `admin_tokens`: the owner, a name, the
sha256 of the value, the visible prefix (`reb_` plus eight characters), created, last
used, revoked. Minted from the admin area or by `rebase createtoken --email`, shown
once and never stored. Presented as `Authorization: Bearer reb_…`. `resolve` answers
the admin behind it or refuses; an unknown value, a revoked token and a deactivated
owner are the same refusal, «Token non valido», so a leaked token is not an oracle.
The same shape as the CRM's `PatService`, written again because the hub imports nothing
from the CRM; without the activity timeline, which the hub does not have.

**Transport.** The same `build_server` served over Streamable HTTP, stateless and with
JSON responses, mounted inside the hub API at `/api/hub/mcp`. The host vhost already
proxies `/api/hub/` to that process, so nothing changes on the host, and no compose
service is added: the API is one process and the transport keeps no session. Stdio
stays for a developer and for the tests, and it needs the same token in
`REBASE_MCP_TOKEN`: `python -m rebase_mcp` refuses to start without one that
resolves. That variable follows REB-211's rename with the others.

**The actor.** The admin behind the token is the author of what the tools write: a
comment, a card drafted from a signup. Over HTTP the admin is resolved per request and
carried on a `ContextVar` for the duration of the call; over stdio it is resolved once
at start-up. «MCP» as a default author goes away: the thread says who.

**Tools.** Everything the admin area shows. The existing twelve plus REB-206's
`read_freelancer_cv`, and one more, `list_pigro_spaces`, which answers what «Istanze
Pigro» shows through `PigroRegistry` and the `HttpCall` seam, with the same two sentences
the page shows when the token is not configured or the CRM does not answer.

**The admin area.** A page «Agenti» (`/hub/admin/agenti`): the endpoint, a name and a
button that mints a token shown once, the admin's own tokens with a revoke on each, and
the two snippets a client takes (the Claude Code command and the JSON block), with the
token filled in once it exists. An admin sees and revokes their own tokens only.

## 2. What exists and is reused

- `AdminUser`, `AdminService` (argon2, cookie sessions, `attivo`), `AdminDep` on every
  admin route, `rebase createadmin` (`packages/core/src/rebase_core/admin.py`,
  `cli.py`, `apps/api/src/rebase_api/deps.py`).
- `build_server(factory)` and the one-session-per-call `_run` in
  `apps/mcp/src/rebase_mcp/server.py`; `__main__.py` for stdio.
- `PigroRegistry.list_spaces` and `GET /api/hub/pigro/istanze`
  (`rebase_core/pigro.py`, `rebase_api/routers/pigro.py`).
- The CRM's design and code for the same problem:
  `projects/pigrocrm/docs/superpowers/specs/2026-09-12-mcp-over-http-and-connect-an-agent-design.md`,
  `pigrocrm_mcp/http.py`, `pigrocrm_mcp/actor_scope.py`, the «Collega un agente»
  dialog. Read, not imported.

## 3. The pieces

### 3.1 Core

- `models.AdminToken` and migration `0010_admin_tokens`: `admin_tokens(id, admin_id →
  admin_users.id, nome, token_hash unique, prefix, created_at, updated_at,
  last_used_at, revoked_at)`.
- `rebase_core/admin_tokens.py`: `AdminTokenService(session)` with `create(admin_id,
  nome) -> (AdminTokenRead, raw)`, `list(admin_id)`, `revoke(admin_id, token_id)` and
  `resolve(raw) -> AdminRead`, which stamps `last_used_at` and refuses with one
  `ValidationFailed("token", "token", "Token non valido")` for every failure.
- `rebase createtoken --email a@b.it [--nome "Claude Code"]`: prints the raw value
  once, for the operator who has no browser at hand, which is how the first token in
  production is minted.

### 3.2 API

- `routers/tokens.py`: `GET /api/hub/tokens` (the caller's own, newest first),
  `POST /api/hub/tokens` (`{nome}` → the row plus `token`, the one response that carries
  the value), `DELETE /api/hub/tokens/{id}` (204; 404 for another admin's token).
- `main.py` mounts the MCP transport at `/api/hub/mcp` and enters its lifespan in the
  app's own, so the SDK's session manager runs for the life of the process.

### 3.3 MCP

- `build_server(factory, admin, *, settings=None, http=None)`: `admin` is a callable
  answering the current `AdminRead`, so the transport decides how it is resolved.
  `settings` and `http` are what `list_pigro_spaces` needs; without them the tool
  answers the «not configured» sentence.
- `rebase_mcp/http.py`: a pure ASGI application, `McpHttpApp(factory, settings,
  http)`. `POST`/`GET`/`DELETE` on its root path go through `_bearer_of` and
  `AdminTokenService.resolve` in a worker thread; a missing or bad token is a 401 with
  `www-authenticate: Bearer`; the admin is stamped on the scope's `state` and a
  server middleware binds it to a `ContextVar` for the handler. One `MCPServer` for the
  process, built once, since the tool list does not depend on who is calling.
- `__main__.py`: reads `REBASE_MCP_TOKEN`, resolves it once with a session of its
  own, refuses with a sentence on stderr otherwise, then serves stdio with that admin.

### 3.4 Web

- `lib/api.ts`: `admin.tokens()`, `admin.createToken(nome)`, `admin.revokeToken(id)`,
  the `AdminToken` shape.
- `pages/admin/Agenti.tsx`, route `/admin/agenti`, nav entry «Agenti» after
  «Amministratori». Endpoint read-only with copy; the mint form (name prefilled «Claude
  Code»); the token once, monospace, with copy and the warning that it is a password;
  the list with prefix, name, created, last used, and «Revoca» with a confirm; the two
  snippets. `lib/connect.ts` holds the pure snippet builders so the test reads strings.

## 4. Verification

- Core: a token resolves to its admin; revoked, unknown and deactivated-owner all answer
  the same sentence; `list` is the owner's only; the migration test's `compare_metadata`
  is empty.
- API: the three routes behind the cookie and 401 without; another admin's token is 404
  on revoke; the raw value appears in the `POST` answer and nowhere else.
- MCP: over HTTP through `httpx` `ASGITransport` and the SDK's own client, as the CRM
  tests do: 401 uniform without a token, the tool list with one, a comment written over
  HTTP signed with the admin's name, `list_pigro_spaces` through a fake `HttpCall`.
  Stdio: `__main__` refuses without the variable.
- Web: the page mints, shows once, lists and revokes, with `fetch` mocked, as
  `Admins.test.tsx` does.
- Production, after the tag: mint a token for Ivan with `rebase createtoken`, point
  his client at `https://letsrebase.com/api/hub/mcp`, list the tools, read one CV, then
  remove the ssh entry.

## 5. Out of scope

OAuth and the claude.ai connectors (the CRM's reasoning, unchanged). Tokens for members.
A token that opens PigroCRM. Expiry on tokens. A separate `mcp` service.
