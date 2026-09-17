/** REB-273: the token must be out of the URL before anything else can see it. */
import { afterEach, describe, expect, it } from 'vitest'
import { stripEntraToken, takeEntraToken } from './entra-token'

function setLocation(path: string) {
  window.history.replaceState(null, '', path)
}

afterEach(() => {
  // Whatever a test left behind, in the URL and in the module's own one-shot slot.
  setLocation('/hub/')
  takeEntraToken()
})

describe('stripEntraToken', () => {
  it('takes the token out of the URL', () => {
    setLocation('/hub/entra?t=abc123')
    stripEntraToken()
    expect(window.location.search).toBe('')
    expect(takeEntraToken()).toBe('abc123')
  })

  it('keeps other params and only removes t', () => {
    setLocation('/hub/entra?t=abc123&x=1')
    stripEntraToken()
    expect(window.location.search).toBe('?x=1')
    expect(takeEntraToken()).toBe('abc123')
  })

  it('is consumed once: a second read finds nothing', () => {
    setLocation('/hub/entra?t=abc123')
    stripEntraToken()
    expect(takeEntraToken()).toBe('abc123')
    expect(takeEntraToken()).toBeNull()
  })

  it('does nothing off the entra path, token left in the URL', () => {
    setLocation('/hub/accedi?t=abc123')
    stripEntraToken()
    expect(window.location.search).toBe('?t=abc123')
    expect(takeEntraToken()).toBeNull()
  })

  it('does nothing on entra with no token', () => {
    setLocation('/hub/entra')
    stripEntraToken()
    expect(window.location.pathname).toBe('/hub/entra')
    expect(window.location.search).toBe('')
    expect(takeEntraToken()).toBeNull()
  })
})
