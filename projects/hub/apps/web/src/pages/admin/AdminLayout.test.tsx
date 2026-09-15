import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  Outlet,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminLayout } from './AdminLayout'

vi.mock('@rebase/analytics/browser', () => ({
  capture: vi.fn(),
  identifyUser: vi.fn(),
  resetUser: vi.fn(),
}))
import { identifyUser, resetUser } from '@rebase/analytics/browser'
import { ME_KEY } from '@/lib/auth'

const IVAN = { id: 'a1', email: 'ivan@rebase.it', nome: 'Ivan', attivo: true, created_at: '2026-09-10T10:00:00Z' }

function answer(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mount() {
  const root = createRootRoute({ component: () => <Outlet /> })
  const login = createRoute({ getParentRoute: () => root, path: '/admin/login', component: () => <h1>Login</h1> })
  const area = createRoute({ getParentRoute: () => root, path: '/admin', component: AdminLayout })
  const freelance = createRoute({ getParentRoute: () => area, path: '/freelance', component: () => <h1>Dentro</h1> })
  const router = createRouter({
    routeTree: root.addChildren([login, area.addChildren([freelance])]),
    history: createMemoryHistory({ initialEntries: ['/admin/freelance'] }),
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return client
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('the admin frame and PostHog (ORB-185)', () => {
  it('identifies the admin once the session is known, with the role', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, IVAN))
    mount()
    await screen.findByRole('heading', { name: 'Dentro' })
    expect(identifyUser).toHaveBeenCalledTimes(1)
    expect(identifyUser).toHaveBeenCalledWith('a1', { email: 'ivan@rebase.it', nome: 'Ivan', ruolo: 'admin' })
  })

  it('identifies the same admin once, however many times the session is fetched again', async () => {
    // A fresh Response per call: a body can be read once, and this test reads two.
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => answer(200, IVAN))
    const client = mount()
    await screen.findByRole('heading', { name: 'Dentro' })
    await client.invalidateQueries({ queryKey: ME_KEY })
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2))
    expect(identifyUser).toHaveBeenCalledTimes(1)
  })

  it('identifies nobody without a session, and sends the visitor to the login', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(401, { detail: 'Autenticazione richiesta' }))
    mount()
    await screen.findByRole('heading', { name: 'Login' })
    expect(identifyUser).not.toHaveBeenCalled()
  })

  it('forgets the admin on Esci, before the page leaves', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, IVAN))
    // The logout ends in `window.location.assign`, which jsdom cannot do and says so
    // once on the console (from its own console, out of a spy's reach); the assertion
    // is about what happens before it.
    mount()
    await screen.findByRole('heading', { name: 'Dentro' })
    await userEvent.setup().click(screen.getByRole('button', { name: /Esci/ }))
    await waitFor(() => expect(resetUser).toHaveBeenCalledTimes(1))
  })
})
