/**
 * What a link to this site shares with (ORB-112).
 *
 * Every page of the site, not the four `landing-pages.test.ts` covers: a link to the
 * pitch or to the community page is shared as readily as a link to the front door, and
 * the head that forgets these tags is the one nobody looks at. Until this existed the
 * pages named a title and a description and no image, so a client fell back to the
 * first large picture in the markup, which on the landing is one of the four faces in
 * the voices section, and Ivan's own face is the first of them.
 */
import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { route } from './path-map-plugin'

const PAGES = [
  'index.html',
  'pigrocrm.html',
  'orbiters.html',
  'pitch.html',
  'privacy.html',
  'termini.html',
] as const

const CARD_PATH = '/assets/share-card.png'
const CARD_URL = `https://letsrebase.com${CARD_PATH}`
const CARD_FILE = join(__dirname, 'public', CARD_PATH)
const WIDTH = 1200
const HEIGHT = 630

const html = Object.fromEntries(
  PAGES.map((name) => [name, readFileSync(join(__dirname, name), 'utf-8')]),
) as Record<(typeof PAGES)[number], string>

function meta(page: string, name: string): string | undefined {
  // The alt is long enough that prettier wraps its tag across three lines, so the
  // content may sit on a line of its own: `[\s\S]` rather than `\s`.
  return page.match(new RegExp(`<meta[\\s\\S]*?(?:name|property)="${name}"[\\s\\S]*?content="([^"]*)"`))?.[1]
}

describe.each(PAGES)('%s shares with the card', (name) => {
  const page = html[name]

  it('names the site, the image and the card type', () => {
    expect(meta(page, 'og:site_name')).toBe('Orbiters')
    expect(meta(page, 'og:image')).toBe(CARD_URL)
    expect(meta(page, 'og:image:width')).toBe(String(WIDTH))
    expect(meta(page, 'og:image:height')).toBe(String(HEIGHT))
    expect(meta(page, 'twitter:card')).toBe('summary_large_image')
  })

  it('describes the image for a reader who cannot see it', () => {
    // A card with no alt is an image a screen reader announces as a filename, and
    // LinkedIn reads this one out in the preview it builds.
    //
    // A word of warning for whoever edits these heads: `landing-pages.test.ts` refuses
    // the string «SLA» anywhere in termini.html, with no word boundary, so a comment
    // there that names a certain chat application fails a test about subscriptions.
    expect((meta(page, 'og:image:alt') ?? '').length).toBeGreaterThan(30)
  })

  it('carries a title and a description to go with it', () => {
    // The pitch had neither until now: `noindex` is about crawling, not about sharing.
    expect(meta(page, 'og:title')).toBeTruthy()
    expect((meta(page, 'og:description') ?? '').length).toBeGreaterThan(40)
  })
})

describe('the card itself', () => {
  it('is served from a path the site actually answers on', () => {
    // nginx serves the six pages and `/assets/`, and 404s the rest (deploy/nginx.conf),
    // so a card at the document root would be a 404 in production and a 200 in preview.
    // `public/assets/` is how a file keeps an unhashed name and still lands there.
    expect(route(CARD_PATH)).toEqual({ kind: 'file' })
    expect(statSync(CARD_FILE).isFile()).toBe(true)
  })

  it('is a PNG of exactly the size the tags promise', () => {
    const png = readFileSync(CARD_FILE)
    expect(png.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    // IHDR is the first chunk: width and height are two big-endian 32-bit integers at
    // byte 16. A card of the wrong size is one LinkedIn crops or refuses to enlarge.
    expect(png.readUInt32BE(16)).toBe(WIDTH)
    expect(png.readUInt32BE(20)).toBe(HEIGHT)
  })

  it('is small enough that every client fetches it', () => {
    // WhatsApp gives up above 600 kB and shows no image at all; this one is about 30.
    expect(statSync(CARD_FILE).size).toBeLessThan(600_000)
  })

  it('is drawn from the shared palette rather than from hexes of its own', () => {
    const script = readFileSync(join(__dirname, '..', 'scripts', 'share-card.mjs'), 'utf-8')
    const hexes = [...script.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((match) => match[0])
    // White is the one literal the card is allowed: it is not a brand token, it is the
    // paper the ink is not, and `system.css` spells `#ffffff` for the same reason.
    expect(hexes.filter((hex) => hex.toLowerCase() !== '#ffffff')).toEqual([])
    expect(script).toContain('palette.css')
  })
})
