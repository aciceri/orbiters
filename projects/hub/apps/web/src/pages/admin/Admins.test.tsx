import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminAdmins } from './Admins'

const IVAN = { id: '1', email: 'ivan@rebase.it', nome: 'Ivan', attivo: true, created_at: '2026-09-10T10:00:00Z' }
const ADA = { id: '2', email: 'ada@rebase.it', nome: 'Ada', attivo: true, created_at: '2026-09-10T11:00:00Z' }

function answer(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AdminAdmins />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('the Amministratori page (REB-279: promote/demote, no password anywhere)', () => {
  it('shows the list and the form on the page, no dialog, no password field', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => answer(200, [IVAN]))
    mount()
    await screen.findByText('ivan@rebase.it')
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Nome')).toBeInTheDocument()
    expect(screen.getByLabelText('Cognome')).toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('promotes an address with one click, posting the email alone when nome/cognome are blank', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    spy.mockResolvedValueOnce(answer(200, [IVAN]))
    spy.mockResolvedValueOnce(answer(200, ADA))
    spy.mockResolvedValueOnce(answer(200, [IVAN, ADA]))
    mount()
    await screen.findByText('ivan@rebase.it')
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'ada@rebase.it')
    await user.click(screen.getByRole('button', { name: 'Promuovi' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Amministratore promosso'))
    expect(screen.getByRole('status')).toHaveTextContent('ada@rebase.it')
    await screen.findByText('ada@rebase.it', { selector: 'td p' })
    const [url, init] = spy.mock.calls[1]!
    expect(url).toBe('/api/hub/admins/promote')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ email: 'ada@rebase.it' })
    // The form is blank again after a successful promotion.
    expect(screen.getByLabelText('Email')).toHaveValue('')
  })

  it('sends nome/cognome too when typed, for a brand-new address', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    spy.mockResolvedValueOnce(answer(200, []))
    spy.mockResolvedValueOnce(answer(201, ADA))
    spy.mockResolvedValueOnce(answer(200, [ADA]))
    mount()
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'ada@rebase.it')
    await user.type(screen.getByLabelText('Nome'), 'Ada')
    await user.type(screen.getByLabelText('Cognome'), 'Lovelace')
    await user.click(screen.getByRole('button', { name: 'Promuovi' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('ada@rebase.it'))
    const [, init] = spy.mock.calls[1]!
    expect(JSON.parse(init?.body as string)).toEqual({ email: 'ada@rebase.it', nome: 'Ada', cognome: 'Lovelace' })
  })

  it('keeps a refused promotion on the field the server names', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    spy.mockResolvedValueOnce(answer(200, [IVAN]))
    spy.mockResolvedValueOnce(
      answer(422, { detail: [{ loc: ['body', 'email'], msg: 'indirizzo già usato da un altro account' }] }),
    )
    mount()
    await screen.findByText('ivan@rebase.it')
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'occupato@rebase.it')
    await user.click(screen.getByRole('button', { name: 'Promuovi' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('indirizzo già usato da un altro account')
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    // The draft stays, so the person corrects the one field rather than retyping.
    expect(screen.getByLabelText('Email')).toHaveValue('occupato@rebase.it')
  })

  it('demotes a row on the click, no confirmation dialog, fully reversible', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    spy.mockResolvedValueOnce(answer(200, [IVAN, ADA]))
    spy.mockResolvedValueOnce(answer(200, ADA))
    spy.mockResolvedValueOnce(answer(200, [IVAN]))
    mount()
    await screen.findByText('ada@rebase.it')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Rimuovi.*Ada.*ada@rebase\.it/s }))
    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Non è più amministratore'))
    expect(screen.getByRole('status')).toHaveTextContent('ada@rebase.it')
    const [url, init] = spy.mock.calls[1]!
    expect(url).toBe('/api/hub/admins/2/demote')
    expect(init?.method).toBe('POST')
  })
})
