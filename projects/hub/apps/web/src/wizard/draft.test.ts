import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DRAFT_TTL_MS, clearDraft, loadDraft, saveDraft } from './draft'

interface Form {
  nome: string
  email: string
  links: string[]
  cv: File | null
}

const KEY = 'rebase.wizard.test'

describe('the wizard draft', () => {
  beforeEach(() => window.localStorage.clear())
  afterEach(() => {
    window.localStorage.clear()
    vi.useRealTimers()
  })

  it('is nothing until something was saved', () => {
    expect(loadDraft<Form>(KEY)).toBeNull()
  })

  it('gives back the answers and the step they were at', () => {
    saveDraft<Form>(KEY, { nome: 'Ada', email: 'ada@studio.it', links: ['https://a.dev'], cv: null }, 2)
    expect(loadDraft<Form>(KEY)).toEqual({
      value: { nome: 'Ada', email: 'ada@studio.it', links: ['https://a.dev'], cv: null },
      index: 2,
    })
  })

  it('leaves a File out: it cannot be stored, and the person picks it again', () => {
    const cv = new File(['%PDF'], 'cv.pdf', { type: 'application/pdf' })
    saveDraft<Form>(KEY, { nome: 'Ada', email: '', links: [], cv }, 3)
    expect(loadDraft<Form>(KEY)?.value).toEqual({ nome: 'Ada', email: '', links: [] })
  })

  it('forgets a draft older than its life', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-15T20:00:00Z'))
    saveDraft<Form>(KEY, { nome: 'Ada', email: '', links: [], cv: null }, 1)
    vi.setSystemTime(new Date('2026-09-15T20:00:00Z').getTime() + DRAFT_TTL_MS + 1)
    expect(loadDraft<Form>(KEY)).toBeNull()
    // And it is gone from storage too, not only refused.
    expect(window.localStorage.getItem(KEY)).toBeNull()
  })

  it('is empty after a blank draft: nothing typed is nothing to keep', () => {
    saveDraft<Form>(KEY, { nome: '', email: '', links: [], cv: null }, 0)
    expect(loadDraft<Form>(KEY)).toBeNull()
  })

  it('ignores what it cannot read', () => {
    window.localStorage.setItem(KEY, '{not json')
    expect(loadDraft<Form>(KEY)).toBeNull()
    window.localStorage.setItem(KEY, JSON.stringify({ v: 99, value: { nome: 'x' }, index: 1, savedAt: Date.now() }))
    expect(loadDraft<Form>(KEY)).toBeNull()
  })

  it('is cleared on purpose', () => {
    saveDraft<Form>(KEY, { nome: 'Ada', email: '', links: [], cv: null }, 1)
    clearDraft(KEY)
    expect(loadDraft<Form>(KEY)).toBeNull()
  })

  it('survives a storage that refuses', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => saveDraft<Form>(KEY, { nome: 'Ada', email: '', links: [], cv: null }, 1)).not.toThrow()
    setItem.mockRestore()
  })
})
