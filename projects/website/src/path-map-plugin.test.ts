import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ELSEWHERE, GENERATED_PATHS, PAGES, REDIRECTS, SITE_HOST, pathMapPlugin, route } from './path-map-plugin'

const nginx = readFileSync(join(__dirname, '..', 'deploy', 'nginx.conf'), 'utf-8')
const vhost = readFileSync(join(__dirname, '..', 'deploy', 'letsrebase.conf'), 'utf-8')

/** The exact-match locations of nginx.conf, as two maps shaped like the plugin's own. */
function nginxMap(conf: string): { pages: Record<string, string>; redirects: Record<string, string> } {
  const pages: Record<string, string> = {}
  const redirects: Record<string, string> = {}
  for (const [, path, file, to] of conf.matchAll(
    /^\s*location = (\S+)\s*\{\s*(?:try_files (\S+) =404|return 301 (\S+));\s*\}/gm,
  )) {
    if (file) pages[path!] = file
    // `$is_args$args` is how nginx says "carry the query string", which the dev server
    // does in code instead (`handle`), so the target compared here is the path alone.
    if (to) redirects[path!] = to.replace('$is_args$args', '')
  }
  return { pages, redirects }
}

describe('the path map, against deploy/nginx.conf', () => {
  it('serves the same file at each path nginx does, and no other', () => {
    // GENERATED_PATHS have no rollup input in vite.config.ts; this plugin writes them
    // into the build output itself (see the robots.txt describe block below), but
    // nginx serves them with the same `try_files <path> =404` shape as every page, so
    // they still have to appear here for the two files to agree.
    const generatedAsPages = Object.fromEntries(GENERATED_PATHS.map((path) => [path, path]))
    expect({ ...PAGES, ...generatedAsPages }).toEqual(nginxMap(nginx).pages)
  })

  it('redirects the same paths to the same places', () => {
    expect(REDIRECTS).toEqual(nginxMap(nginx).redirects)
  })

  it('carries the query string through the redirect, so an old ad link keeps its utm_*', () => {
    expect(nginx).toMatch(/location = \/orbiters \{ return 301 \/community\$is_args\$args; \}/)
  })

  it('reads at least the four pages out of nginx.conf, so a reformatted file cannot pass as an empty map', () => {
    expect(Object.keys(nginxMap(nginx).pages).length).toBeGreaterThanOrEqual(4)
  })

  it('mirrors an nginx that 404s everything it was not told about', () => {
    expect(nginx).toMatch(/location \/ \{ return 404; \}/)
    expect(nginx).not.toMatch(/try_files \$uri \/index\.html/)
  })

  it('names only tenants the host vhost actually routes away from the container', () => {
    for (const prefix of Object.keys(ELSEWHERE)) {
      expect(vhost, `${prefix} in letsrebase.conf`).toMatch(
        new RegExp(`^\\s*location\\s+(?:=|\\^~)?\\s*${prefix}[/\\s]`, 'm'),
      )
    }
  })
})

describe('route', () => {
  it('puts the landing at the front door, the community page at /community, and redirects its old name (ORB-145, REB-212)', () => {
    expect(route('/')).toEqual({ kind: 'page', file: '/index.html' })
    expect(route('/community')).toEqual({ kind: 'page', file: '/community.html' })
    expect(route('/orbiters')).toEqual({ kind: 'redirect', to: '/community' })
    expect(route('/pitch')).toEqual({ kind: 'page', file: '/pitch.html' })
    expect(route('/privacy')).toEqual({ kind: 'page', file: '/privacy.html' })
    expect(route('/termini')).toEqual({ kind: 'page', file: '/termini.html' })
  })

  it('serves PigroCRM its own page at /pigrocrm again (ORB-159), and keeps no redirect of its own', () => {
    expect(route('/pigrocrm')).toEqual({ kind: 'page', file: '/pigrocrm.html' })
    expect(REDIRECTS['/pigrocrm']).toBeUndefined()
  })

  it('404s what nginx 404s: unknown paths, trailing slashes, and the files under their own names', () => {
    for (const path of ['/nonexistent', '/pigrocrm/', '/privacy/', '/index.html', '/community.html', '/privacy.html']) {
      expect(route(path), path).toEqual({ kind: 'not-found' })
    }
  })

  it('lets the built assets, the sources and the dev client through, with no html fallback behind them', () => {
    for (const path of ['/assets/landing-BwJRpj9t.css', '/community.js', '/rebase-logo.svg', '/@vite/client', '/@fs/x/y.ts']) {
      expect(route(path), path).toEqual({ kind: 'file' })
    }
  })

  it('proxies /api and answers a stand-in for the other tenants of the origin, whole prefixes only', () => {
    expect(route('/api/community/signups')).toEqual({ kind: 'proxy' })
    expect(route('/app/')).toMatchObject({ kind: 'elsewhere' })
    expect(route('/app')).toMatchObject({ kind: 'elsewhere' })
    expect(route('/hub/freelance')).toMatchObject({ kind: 'elsewhere' })
    expect(route('/health')).toMatchObject({ kind: 'elsewhere' })
    // `/apple` is not `/app/`: a prefix match that ignored the slash would hand a real
    // 404 to a fictional tenant.
    expect(route('/apple')).toEqual({ kind: 'not-found' })
    expect(route('/hubris')).toEqual({ kind: 'not-found' })
  })
})

describe('robots.txt (REB-109)', () => {
  it('has its own exact-match location in nginx.conf, like every page', () => {
    expect(nginx).toMatch(/location = \/robots\.txt \{ try_files \/robots\.txt =404; \}/)
  })

  it('names the sitemap and disallows the noindex pages, nothing else', () => {
    const decision = route('/robots.txt')
    expect(decision.kind).toBe('generated')
    if (decision.kind !== 'generated') throw new Error('unreachable')
    expect(decision.contentType).toBe('text/plain; charset=utf-8')
    expect(decision).toMatchObject({
      content: `User-agent: *\nDisallow: /pitch\nSitemap: ${SITE_HOST}/sitemap.xml\n`,
    })
  })

  it('is written into the build output by the plugin\'s own writeBundle hook', () => {
    const dir = mkdtempSync(join(tmpdir(), 'website-robots-'))
    const plugin = pathMapPlugin()
    if (typeof plugin.writeBundle !== 'function') throw new Error('writeBundle is not a plain function')
    plugin.writeBundle.call({} as never, { dir } as never, {} as never)
    const builtPath = join(dir, 'robots.txt')
    expect(existsSync(builtPath)).toBe(true)
    expect(readFileSync(builtPath, 'utf-8')).toContain(`Sitemap: ${SITE_HOST}/sitemap.xml`)
  })
})
