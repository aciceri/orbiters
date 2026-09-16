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
    expect(vhost).toMatch(/add_header X-Robots-Tag "noindex, nofollow, noarchive" always;/)
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
