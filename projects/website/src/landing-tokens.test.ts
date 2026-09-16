import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { extractSharedTokens } from './palette-plugin'

const shared = extractSharedTokens(readFileSync(fileURLToPath(import.meta.resolve('@rebase/brand/palette.css')), 'utf-8'))
const landingCss = readFileSync(join(__dirname, 'landing.css'), 'utf-8')
const pitchCss = readFileSync(join(__dirname, 'pitch.css'), 'utf-8')

type Triple = [number, number, number]

function toLinear(channel: number): number {
  const c = channel / 255
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

function hexToRgb(hex: string): Triple {
  const v = hex.replace('#', '')
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)]
}

function relativeLuminance([r, g, b]: Triple): number {
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b)
}

/** WCAG 2.x contrast ratio, order-independent. Same formula as tokens.test.ts. */
function contrastRatio(hexA: string, hexB: string): number {
  const a = relativeLuminance(hexToRgb(hexA))
  const b = relativeLuminance(hexToRgb(hexB))
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

const LANDING_DECLARATION = /--landing-[\w-]+\s*:\s*[^;]+;/g
// pitch.css keeps its own short names (REB-248): longest alternative first, so
// `--melon-strong` is not cut short by `--melon` matching its own prefix.
const PITCH_DECLARATION = /--(?:ink|quiet|paper|gold|melon-strong|melon)\s*:\s*[^;]+;/g
const VAR = /^var\((--color-[\w-]+)\)$/

function declaredValue(token: string, css: string): string {
  const match = css.match(new RegExp(`${token}\\s*:\\s*([^;]+);`))
  const value = match?.[1]
  if (!value) throw new Error(`${token} is not declared`)
  return value.trim()
}

/** Resolves a --landing-* colour token to the sRGB hex a browser would compute. Every
 *  text colour on the landing is now a plain var() of a shared token: the opaque box
 *  replaced the tinted veils, so there is no color-mix toward white left to resolve.
 *  `--landing-grid`, `--landing-cell` and `--landing-step` are a line, a length and a
 *  length, not text colours, and are not read through here. */
function resolveLandingColour(token: string): string {
  const value = declaredValue(token, landingCss)
  const direct = VAR.exec(value)
  if (!direct) throw new Error(`${token} is not var(--color-…): ${value}`)
  const hex = shared[direct[1] ?? '']
  if (!hex) throw new Error(`${token} points at ${direct[1]}, which tokens.css does not define`)
  return hex
}

/** Same resolution for pitch.css's own six names. `--grid`, `--cell`, `--step` and
 *  `--ease` are a line, two lengths and a curve, not colours, and are not read here. */
function resolvePitchColour(token: string): string {
  const value = declaredValue(token, pitchCss)
  const direct = VAR.exec(value)
  if (!direct) throw new Error(`${token} is not var(--color-…): ${value}`)
  const hex = shared[direct[1] ?? '']
  if (!hex) throw new Error(`${token} points at ${direct[1]}, which tokens.css does not define`)
  return hex
}

describe('landing tokens', () => {
  it('resolves every --landing-* colour out of the shared palette', () => {
    expect(resolveLandingColour('--landing-surface')).toBe('#f1f2f3')
    expect(resolveLandingColour('--landing-ink')).toBe('#011936')
    expect(resolveLandingColour('--landing-ink-quiet')).toBe('#465362')
    expect(resolveLandingColour('--landing-cta')).toBe('#e5133e')
    expect(resolveLandingColour('--landing-focus')).toBe('#ed254e')
  })

  it('contains no raw hexadecimal in the --landing-* block, other than white', () => {
    // White is the neutral a tint is mixed toward, not a sixth colour. Everything
    // else must be a var(--color-…) or a color-mix() of one, which is what makes
    // forking the palette mechanically impossible rather than discouraged.
    for (const declaration of landingCss.match(LANDING_DECLARATION) ?? []) {
      for (const hex of declaration.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []) {
        expect(hex.toLowerCase(), `raw hex in ${declaration}`).toBe('#ffffff')
      }
    }
  })

  it('reaches 4.5:1 on every text pair', () => {
    const surface = resolveLandingColour('--landing-surface')
    const ink = resolveLandingColour('--landing-ink')
    const quiet = resolveLandingColour('--landing-ink-quiet')
    // Boxes and cards are opaque white, so every text colour is also read on white.
    for (const [text, background] of [
      [ink, surface],
      [quiet, surface],
      [ink, '#ffffff'],
      [quiet, '#ffffff'],
      ['#ffffff', resolveLandingColour('--landing-cta')],
    ] as const) {
      expect(contrastRatio(text, background), `${text} on ${background}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('reaches 3:1 on the focus ring, which is a component and not text', () => {
    const ratio = contrastRatio(
      resolveLandingColour('--landing-focus'),
      resolveLandingColour('--landing-surface'),
    )
    expect(ratio).toBeGreaterThanOrEqual(3)
  })

  it('never uses raw Watermelon as a solid fill', () => {
    // The regression banned by name. In the app this is solved: --primary and
    // --destructive both point at --color-watermelon-strong, because white on raw
    // Watermelon is 4.221:1 and misses the 4.5:1 body-text floor. The landing must
    // not re-introduce it on the one element that IS a solid fill under white
    // text: the call to action.
    for (const [, property, value] of landingCss.matchAll(
      /(?:^|[;{])\s*(background|background-color|fill)\s*:\s*([^;}]+)/g,
    )) {
      expect(value, `${property} fills with raw Watermelon`).not.toMatch(
        /--color-watermelon(?!-strong)/,
      )
      expect(value, `${property} fills with #ed254e`).not.toMatch(/#ed254e/i)
    }
  })

  it('loads no webfont other than Outfit, and none from a CDN', () => {
    expect(landingCss).not.toMatch(/Reenie/i)
    expect(landingCss).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/)
    // The sheet must not declare a face of its own: the typeface is the brand's and
    // arrives from `@rebase/brand/font.css`, prepended by the palette plugin. Two
    // @font-face blocks for one family is how a landing ends up on a stale copy.
    expect(landingCss).not.toMatch(/@font-face/)
    // Comments stripped first: that file's own comment explains at length why it does
    // not fetch from Google, and the check is about what the browser requests.
    const brandFont = readFileSync(
      fileURLToPath(import.meta.resolve('@rebase/brand/font.css')),
      'utf-8',
    ).replace(/\/\*[\s\S]*?\*\//g, '')
    expect(brandFont).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/)
    const families = [...brandFont.matchAll(/@font-face\s*\{[^}]*font-family:\s*'([^']+)'/g)].map(
      (m) => m[1],
    )
    expect(families).toEqual(['Outfit'])
  })
})

// pitch.css joined TOKEN_CONSUMERS in REB-248: it used to restate the six colours and
// its own @font-face, a latent fork of shared/brand that a palette change would have
// left the deck on. These hold the same two guarantees landing.css already had.
describe('pitch deck tokens', () => {
  it('resolves every pitch colour variable out of the shared palette', () => {
    expect(resolvePitchColour('--ink')).toBe('#011936')
    expect(resolvePitchColour('--quiet')).toBe('#465362')
    expect(resolvePitchColour('--paper')).toBe('#f1f2f3')
    expect(resolvePitchColour('--gold')).toBe('#f9dc5c')
    expect(resolvePitchColour('--melon')).toBe('#ed254e')
    expect(resolvePitchColour('--melon-strong')).toBe('#e5133e')
  })

  it('contains no raw hexadecimal in its colour variables, other than white', () => {
    for (const declaration of pitchCss.match(PITCH_DECLARATION) ?? []) {
      for (const hex of declaration.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []) {
        expect(hex.toLowerCase(), `raw hex in ${declaration}`).toBe('#ffffff')
      }
    }
  })

  it('declares no @font-face of its own, since palette-plugin.ts prepends the brand font', () => {
    expect(pitchCss).not.toMatch(/@font-face/)
    expect(pitchCss).toMatch(/font-family:\s*var\(--font-sans\)/)
  })
})
