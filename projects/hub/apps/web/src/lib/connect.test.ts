import { describe, expect, it } from 'vitest'
import { SERVER_NAME, TOKEN_PLACEHOLDER, claudeCodeCommand, mcpEndpoint, mcpServersJson } from './connect'

describe('the snippets for connecting an agent (REB-213)', () => {
  it('point at /api/hub/mcp on the page origin, under one server name', () => {
    const url = mcpEndpoint('https://letsrebase.com')
    expect(url).toBe('https://letsrebase.com/api/hub/mcp')
    expect(claudeCodeCommand(url, 'reb_abc')).toBe(
      `claude mcp add --transport http ${SERVER_NAME} https://letsrebase.com/api/hub/mcp --header "Authorization: Bearer reb_abc"`,
    )
    expect(JSON.parse(mcpServersJson(url, TOKEN_PLACEHOLDER))).toEqual({
      mcpServers: { [SERVER_NAME]: { type: 'http', url, headers: { Authorization: 'Bearer <token>' } } } ,
    })
  })
})
