import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { extractSharedTokens } from './palette-plugin'

const shared = extractSharedTokens(readFileSync(fileURLToPath(import.meta.resolve('@rebase/brand/palette.css')), 'utf-8'))
const landingCss = readFileSync(join(__dirname, 'landing.css'), 'utf-8')
const pitchCss = readFileSync(join(__dirname, 'pitch.css'), 'utf-8')
const pigrocrmCss = readFileSync(join(__dirname, 'pigrocrm.css'), 'utf-8')
const pigrocrmHtml = readFileSync(join(__dirname, 'pigrocrm.html'), 'utf-8')

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
// pitch.css keeps its own short names (REB-248): the pattern reaches only these six
// declarations, never the many `var(--ink)`-style uses that follow them.
const PITCH_DECLARATION = /--(?:ink|quiet|paper|gold|melon-strong|melon)\s*:\s*[^;]+;/g
const VAR = /^var\((--color-[\w-]+)\)$/

function declaredValue(token: string, css: string): string {
  const match = css.match(new RegExp(`${token}\\s*:\\s*([^;]+);`))
  const value = match?.[1]
  if (!value) throw new Error(`${token} is not declared`)
  return value.trim()
}

/** Resolves a colour token declared as `var(--color-…)` in the given sheet to the
 *  sRGB hex a browser would compute, against either sheet: every text colour on the
 *  landing and on the deck is now a plain var() of a shared token, so there is no
 *  color-mix toward white left to resolve. `--landing-grid`/`--grid`,
 *  `--landing-cell`/`--cell` and `--landing-step`/`--step` are a line and lengths, not
 *  colours, and are not read through here. */
function resolveColour(token: string, css: string): string {
  const value = declaredValue(token, css)
  const direct = VAR.exec(value)
  if (!direct) throw new Error(`${token} is not var(--color-…): ${value}`)
  const hex = shared[direct[1] ?? '']
  if (!hex) throw new Error(`${token} points at ${direct[1]}, which tokens.css does not define`)
  return hex
}

const DIRECT_HEX = /^#[0-9a-fA-F]{3,8}$/
const LANDING_VAR = /^var\((--landing-[\w-]+)\)$/

/** Every `--landing-*` custom property declared in the given sheet's `:root`,
 *  resolved to a plain hex where that is possible: a `var(--color-…)` value through
 *  `shared`, a literal `#ffffff` as-is, and a `color-mix()` (the grid line, the tile
 *  and the two on-ink overlays) skipped, since none of `pigrocrm.css`'s own `color`
 *  or `background` declarations resolve through one. */
function landingVars(css: string): Record<string, string> {
  const vars: Record<string, string> = {}
  const root = css.match(/:root\s*\{([^}]*)\}/)?.[1] ?? ''
  for (const declaration of root.matchAll(/(--landing-[\w-]+)\s*:\s*([^;]+);/g)) {
    const name = declaration[1]
    const value = declaration[2]?.trim()
    if (!name || !value) continue
    if (DIRECT_HEX.test(value)) {
      vars[name] = value.toLowerCase()
      continue
    }
    const colourVar = VAR.exec(value)
    if (colourVar) {
      const hex = shared[colourVar[1] ?? '']
      if (hex) vars[name] = hex
    }
  }
  return vars
}

/** Strips comments and every `@media`/`@font-face`/`@keyframes` block: REB-267's own
 *  `@media (min-width: 60rem)` addition to `pigrocrm.css` carries a `min-block-size`,
 *  no colour, and stripping it here keeps the one-rule-at-a-time scan below from
 *  having to nest braces for a block it would find nothing in anyway. */
function stripAtRules(css: string): string {
  return css
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/@(?:media|font-face|keyframes)[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, '')
}

type ColourRule = { selector: string; value: string }

/** A declared value resolved to a plain hex where that is mechanical: a literal
 *  `#rgb`/`#rrggbb`, or a `var(--landing-…)` through `vars`. A `color-mix()` (the
 *  grid line, the two on-ink text/rule overlays, the light band's veil) is not
 *  resolved here: none of `pigrocrm.css`'s own declarations use one, and the callers
 *  below treat "cannot resolve" as "skip this element" rather than fall back to a
 *  less specific rule that happens to resolve -- the wrong colour is worse than no
 *  pair. */
function resolveValue(value: string, vars: Record<string, string>): string | undefined {
  if (DIRECT_HEX.test(value)) {
    const hex = value.toLowerCase()
    return hex.length === 4 ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}` : hex
  }
  return vars[LANDING_VAR.exec(value)?.[1] ?? '']
}

/** Every rule in `css` that declares the given property, next to the selector list
 *  it was declared on, value left unresolved -- the building blocks the DOM walk
 *  below crosses against `pigrocrm.html`'s real markup, so a new `color` or
 *  `background` `pigrocrm.css` adds is read the next run rather than typed in here. */
function extractDeclarations(css: string, property: 'color' | 'background'): ColourRule[] {
  const pattern = property === 'color' ? /(?:^|;)\s*color\s*:\s*([^;]+);/ : /background(?:-color)?\s*:\s*([^;]+);/
  const rules: ColourRule[] = []
  for (const rule of stripAtRules(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = rule[1]?.trim()
    const body = rule[2]
    if (!selector || selector === ':root' || !body) continue
    const value = body.match(pattern)?.[1]?.trim()
    if (!value) continue
    rules.push({ selector, value })
  }
  return rules
}

/** CSS specificity of a selector list, the highest among its comma-separated
 *  alternatives (`.matches()` succeeds on any one of them, and that is the
 *  alternative actually competing in the cascade for this element). Neither sheet
 *  uses an id or `!important`, so ids are counted for completeness but never seen;
 *  a pseudo-element counts for nothing; it selects a box no text rule here targets. */
function specificity(selectorList: string): number {
  const scores = selectorList.split(',').map((selector) => {
    const tokens = selector.match(/::[\w-]+|:[\w-]+(?:\([^)]*\))?|#[\w-]+|\.[\w-]+|\[[^\]]*\]|[A-Za-z][\w-]*/g) ?? []
    let score = 0
    for (const token of tokens) {
      if (token.startsWith('::')) continue
      else if (token.startsWith('#')) score += 100
      else if (token.startsWith('.') || token.startsWith(':') || token.startsWith('[')) score += 10
      else score += 1
    }
    return score
  })
  return Math.max(0, ...scores)
}

/** The rule that would actually paint on `element`: the highest-specificity match
 *  among `rules`, ties broken by array order (`landing.css` then `pigrocrm.css`, the
 *  order both call sites below build these in, is the order the cascade loads them
 *  in). Without this, `landing.css`'s base `p, li { color: var(--landing-ink-quiet) }`
 *  (line 256) would pair with every `<p class="kicker">` too, alongside the
 *  `.kicker` rule that actually wins there -- a real cascade conflict, not a
 *  contrast bug. */
function winningRule(rules: ColourRule[], element: Element): ColourRule | undefined {
  let best: { rule: ColourRule; specificity: number; index: number } | undefined
  rules.forEach((rule, index) => {
    let matches = false
    try {
      matches = element.matches(rule.selector)
    } catch {
      // A selector jsdom cannot evaluate (an unsupported pseudo-class) describes no
      // static element, so it wins nothing here.
    }
    if (!matches) return
    const score = specificity(rule.selector)
    if (!best || score > best.specificity || (score === best.specificity && index > best.index)) {
      best = { rule, specificity: score, index }
    }
  })
  return best?.rule
}

/** For every element some `colourRules` entry could apply to, the pair it actually
 *  renders: the winning colour, per `winningRule`, against the nearest ancestor-or-
 *  self's winning `background` (self first, since `background` never inherits and
 *  an unpainted element shows whatever is behind it). A level whose winning rule
 *  does not resolve (a `color-mix()`) stops the walk without a pair rather than
 *  reading past it to a deeper ancestor's background that is not, in fact, what
 *  paints there -- the wrong colour is worse than no pair. The page the pair
 *  actually renders, not one a hand-kept list would guess at. Returns one
 *  `[text, background]` per distinct pair found. */
function derivePairs(
  html: string,
  colourRules: ColourRule[],
  backgroundRules: ColourRule[],
  vars: Record<string, string>,
): [string, string][] {
  document.body.innerHTML = html.match(/<body[^>]*>([\s\S]*)<\/body>/)?.[1] ?? ''
  function nearestBackground(el: Element): string | undefined {
    for (let node: Element | null = el; node; node = node.parentElement) {
      const winner = winningRule(backgroundRules, node)
      if (winner) return resolveValue(winner.value, vars)
    }
    return undefined
  }
  const candidates = new Set<Element>()
  for (const rule of colourRules) {
    try {
      document.querySelectorAll(rule.selector).forEach((element) => candidates.add(element))
    } catch {
      // Same unsupported-pseudo-class case as above: no element to add.
    }
  }
  const pairs = new Map<string, [string, string]>()
  for (const element of candidates) {
    const winner = winningRule(colourRules, element)
    const colour = winner && resolveValue(winner.value, vars)
    if (!colour) continue
    const background = nearestBackground(element)
    if (background) pairs.set(`${colour}|${background}`, [colour, background])
  }
  document.body.innerHTML = ''
  return [...pairs.values()]
}

describe('landing tokens', () => {
  it('resolves every --landing-* colour out of the shared palette', () => {
    expect(resolveColour('--landing-surface', landingCss)).toBe('#f1f2f3')
    expect(resolveColour('--landing-ink', landingCss)).toBe('#011936')
    expect(resolveColour('--landing-ink-quiet', landingCss)).toBe('#465362')
    expect(resolveColour('--landing-cta', landingCss)).toBe('#e5133e')
    expect(resolveColour('--landing-focus', landingCss)).toBe('#ed254e')
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
    const surface = resolveColour('--landing-surface', landingCss)
    const ink = resolveColour('--landing-ink', landingCss)
    const quiet = resolveColour('--landing-ink-quiet', landingCss)
    // Boxes and cards are opaque white, so every text colour is also read on white.
    for (const [text, background] of [
      [ink, surface],
      [quiet, surface],
      [ink, '#ffffff'],
      [quiet, '#ffffff'],
      ['#ffffff', resolveColour('--landing-cta', landingCss)],
    ] as const) {
      expect(contrastRatio(text, background), `${text} on ${background}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('reaches 3:1 on the focus ring, which is a component and not text', () => {
    const ratio = contrastRatio(
      resolveColour('--landing-focus', landingCss),
      resolveColour('--landing-surface', landingCss),
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
    expect(resolveColour('--ink', pitchCss)).toBe('#011936')
    expect(resolveColour('--quiet', pitchCss)).toBe('#465362')
    expect(resolveColour('--paper', pitchCss)).toBe('#f1f2f3')
    expect(resolveColour('--gold', pitchCss)).toBe('#f9dc5c')
    expect(resolveColour('--melon', pitchCss)).toBe('#ed254e')
    expect(resolveColour('--melon-strong', pitchCss)).toBe('#e5133e')
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

// REB-268: /pigrocrm read 4.37:1 on the light band's role line, `.voices-light`
// overriding the ground `landing.css`'s `.who .role` sits on -- a pair the test
// above never saw, because it reads `landing.css` alone. These derive every pair
// `pigrocrm.css` actually renders (its own `color`/`background` declarations, plus
// the `landing.css` ones its markup reaches, crossed against `pigrocrm.html`'s real
// DOM) instead of naming them, so the next override is caught unseen or not at all.
describe('pigrocrm.css text pairs', () => {
  const vars = landingVars(landingCss)
  const colourRules = [...extractDeclarations(landingCss, 'color'), ...extractDeclarations(pigrocrmCss, 'color')]
  const backgroundRules = [...extractDeclarations(landingCss, 'background'), ...extractDeclarations(pigrocrmCss, 'background')]
  const pairs = derivePairs(pigrocrmHtml, colourRules, backgroundRules, vars)

  it('finds at least the pairs the fix above already knows about', () => {
    // A derivation that silently found nothing would pass every assertion below
    // without checking anything -- this is what tells the two apart.
    expect(pairs.length).toBeGreaterThan(0)
  })

  it('reaches 4.5:1 on every text pair pigrocrm.html actually renders', () => {
    for (const [text, background] of pairs) {
      expect(contrastRatio(text, background), `${text} on ${background}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('would have caught REB-268: a light-band override under an existing landing.css text colour', () => {
    // The regression drill: `.role` is `landing.css`'s (`--landing-ink-quiet` on
    // whatever ground it sits on), `.panel` is a synthetic `pigrocrm.css` override,
    // same shape as `.voices-light` -- a background introduced on an ancestor of text
    // this sheet never declares a colour for. Grey-on-grey is the failing "old
    // value"; swapping the override to white is the "new" one derivePairs passes.
    const role = '.who .role { color: var(--landing-ink-quiet); }'
    const html = '<body><div class="panel"><p class="who"><span class="role">hi</span></p></div></body>'
    const roleRules = extractDeclarations(landingCss + role, 'color')
    const failing = derivePairs(html, roleRules, [{ selector: '.panel', value: '#9aa0a6' }], vars)
    expect(failing).toEqual([['#465362', '#9aa0a6']])
    expect(contrastRatio('#465362', '#9aa0a6')).toBeLessThan(4.5)

    const passing = derivePairs(html, roleRules, [{ selector: '.panel', value: '#ffffff' }], vars)
    expect(contrastRatio(...passing[0]!)).toBeGreaterThanOrEqual(4.5)
  })
})
