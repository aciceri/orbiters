/**
 * REB-252: neither nginx layer in front of the CRM set `client_max_body_size`, so an
 * ordinary upload over nginx's own compiled-in 1 MiB default was answered with a bare
 * 413 by `web` (or, on the host, by the vhost) before the request ever reached `api`,
 * whatever the application itself allows -- `DIMENSIONE_MAX`
 * (`packages/core/src/pigrocrm/core/documents/schemas.py:51`, 100 MiB). This asserts
 * all three of the container's and the host's nginx configs carry the same shape: a
 * tight, explicit server-level default (so the limit is versioned rather than left to
 * whatever the `http` block it lands in happens to default to) and a
 * `location ^~ /api/documents/` override that clears the application ceiling, so a
 * regression in either direction -- the directive dropped again, or set below the
 * ceiling it exists to match -- is caught here rather than by the next scanned
 * contract somebody uploads.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Mirrors DIMENSIONE_MAX in packages/core/src/pigrocrm/core/documents/schemas.py: kept
// in bytes here too, so a change to either side is a diff a reviewer can compare
// against the other rather than two numbers that silently drift apart.
const DIMENSIONE_MAX_BYTES = 100 * 1024 * 1024

const pigrocrmRoot = join(__dirname, '..', '..', '..', '..')

const configs: Record<string, string> = {
  'spa.conf (the web container)': readFileSync(
    join(pigrocrmRoot, 'deploy', 'nginx', 'spa.conf'),
    'utf-8',
  ),
  'pigro.letsrebase.conf (the production host)': readFileSync(
    join(pigrocrmRoot, 'deploy', 'nginx', 'pigro.letsrebase.conf'),
    'utf-8',
  ),
  'preview.pigro.letsrebase.conf (the preview host)': readFileSync(
    join(pigrocrmRoot, 'deploy', 'nginx', 'preview.pigro.letsrebase.conf'),
    'utf-8',
  ),
}

function bodySizeBytes(value: string): number {
  const match = value.match(/^(\d+(?:\.\d+)?)([kKmMgG]?)$/)
  if (!match) throw new Error(`unparseable client_max_body_size value: "${value}"`)
  const amount = match[1] ?? ''
  const unit = (match[2] ?? '').toLowerCase()
  const multiplier: Record<string, number> = { k: 1024, m: 1024 ** 2, g: 1024 ** 3 }
  return Number(amount) * (multiplier[unit] ?? 1)
}

describe.each(Object.entries(configs))('%s', (_label, conf) => {
  it('sets a tight, explicit server-level default before the first location', () => {
    // Same slicing robots.test.ts uses for the same reason: nginx does not inherit a
    // directive into a location block that declares its own, so what matters is
    // whether every response not covered by a more specific block gets the tight
    // default, which only a server-level directive guarantees.
    const serverLevel = conf.slice(0, conf.indexOf('\n    location '))
    const matches = [...serverLevel.matchAll(/^\s*client_max_body_size\s+(\S+);/gm)]
    expect(matches, 'no server-level client_max_body_size before the first location').toHaveLength(1)
    const [directive] = matches
    if (!directive) throw new Error('unreachable: length assertion above already failed')
    expect(bodySizeBytes(directive[1] ?? '')).toBeLessThanOrEqual(1024 * 1024)
  })

  it('raises the limit for /api/documents/ to at least the application ceiling', () => {
    const block = conf.match(/location \^~ \/api\/documents\/ \{([\s\S]*?)\n {4}\}/)
    expect(block, 'no location ^~ /api/documents/ block').toBeTruthy()
    if (!block) throw new Error('unreachable: truthy assertion above already failed')
    const directive = block[1]?.match(/client_max_body_size\s+(\S+);/)
    expect(directive, 'no client_max_body_size inside /api/documents/').toBeTruthy()
    if (!directive) throw new Error('unreachable: truthy assertion above already failed')
    expect(bodySizeBytes(directive[1] ?? '')).toBeGreaterThanOrEqual(DIMENSIONE_MAX_BYTES)
  })
})
