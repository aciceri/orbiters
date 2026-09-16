/**
 * REB-107: the CRM host's root redirect carries a real company's name (the root
 * slug) in its `Location`, and nothing stopped a crawler from indexing and
 * republishing it. This asserts the two mechanisms that keep it out of a search
 * result stay in the files that ship them: the vhost's server-level header and
 * `robots.txt` location, and the SPA head's own `<meta name="robots">`, mirrored
 * from `projects/hub/apps/web/index.html`.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const vhost = readFileSync(
  join(__dirname, '..', '..', '..', '..', 'deploy', 'nginx', 'pigro.letsrebase.conf'),
  'utf-8',
)
const html = readFileSync(join(__dirname, '..', '..', 'index.html'), 'utf-8')

describe('the CRM host stays out of search results', () => {
  it('sends X-Robots-Tag on every response, including the root redirect that carries the slug', () => {
    // Pinned to the server-level prologue, not "anywhere in the file": nginx does not
    // inherit `add_header` into a location block that declares its own, so the header
    // only reaches every response (including `location = /` and its 302 carrying the
    // root slug) if it sits before the first `location` -- moving it into, say,
    // `location = /robots.txt` would still match a looser regex here while leaving the
    // root redirect with no header at all.
    const serverLevel = vhost.slice(0, vhost.indexOf('\n    location '))
    expect(serverLevel).toMatch(/add_header X-Robots-Tag "noindex, nofollow, noarchive" always;/)
    // A second `add_header` directive anywhere in a location block would drop the
    // server-level one for that block and every other directive nginx would
    // otherwise inherit into it, silently un-doing the line above for that response.
    // Matched at line start (after indentation) so a comment mentioning the
    // directive by name, like the one above, is not itself counted as one.
    expect(vhost.match(/^\s*add_header\b/gm)).toHaveLength(1)
  })

  it('serves its own robots.txt disallowing everything, rather than letting a crawler get a 404', () => {
    expect(vhost).toMatch(
      /location = \/robots\.txt \{\s*default_type text\/plain;\s*return 200 "User-agent: \*\\nDisallow: \/\\n";\s*\}/,
    )
  })

  it('marks the SPA head noindex too, the same shape as the hub (projects/hub/apps/web/index.html)', () => {
    expect(html).toMatch(/<meta name="robots" content="noindex" \/>/)
  })
})
