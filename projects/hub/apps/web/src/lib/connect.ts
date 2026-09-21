/**
 * What a client needs to talk to the hub's MCP server over HTTP (REB-213): the endpoint,
 * a name for the server, and the two forms a configuration takes. Pure functions, so the
 * page's tests can look at strings.
 */
export const TOKEN_PLACEHOLDER = '<token>'
export const SERVER_NAME = 'rebase-hub'

/** `https://host/api/hub/mcp`: the host vhost proxies it to the `mcp` service. */
export function mcpEndpoint(origin: string): string {
  return `${origin}/api/hub/mcp`
}

export function claudeCodeCommand(url: string, token: string): string {
  return `claude mcp add --transport http ${SERVER_NAME} ${url} --header "Authorization: Bearer ${token}"`
}

export function mcpServersJson(url: string, token: string): string {
  return JSON.stringify(
    { mcpServers: { [SERVER_NAME]: { type: 'http', url, headers: { Authorization: `Bearer ${token}` } } } },
    null,
    2,
  )
}
