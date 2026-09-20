import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  Outlet,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Area } from './Area'

vi.mock('@rebase/analytics/browser', () => ({
  capture: vi.fn(),
}))
import { capture } from '@rebase/analytics/browser'

function answer(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const PROFILE = {
  id: 'f1',
  nome: 'Ada',
  cognome: 'Lovelace',
  email: 'ada@studio.it',
  linkedin_url: 'https://www.linkedin.com/in/ada',
  role: 'member',
  created_at: '2026-09-10T10:00:00Z',
  updated_at: '2026-09-10T10:00:00Z',
  ha_scheda: true,
  cv_filename: 'Ada CV.pdf',
  cv_size: 2048,
  tariffa_giornaliera: '450.00',
  posizione: 'Backend developer',
  remoto: 'ibrido',
  links: ['https://github.com/ada'],
  completa: true,
}

/** The card an admin wrote from Ada's signup (ORB-155): the person has yet to add the
 *  CV, the rate, the position and how she works. */
const INCOMPLETE = {
  ...PROFILE,
  cv_filename: null,
  cv_size: null,
  tariffa_giornaliera: null,
  posizione: null,
  remoto: null,
  completa: false,
}

/** An admin with no freelancer card at all (REB-279): `ha_scheda` false, every card
 *  field blank, `completa` false -- the shape `MeRead` answers for a bare `users` row. */
const CARDLESS_ADMIN = {
  ...PROFILE,
  id: 'a1',
  nome: 'Ivan',
  cognome: 'Fiore',
  email: 'ivan@rebase.it',
  linkedin_url: null,
  role: 'admin',
  ha_scheda: false,
  cv_filename: null,
  cv_size: null,
  tariffa_giornaliera: null,
  posizione: null,
  remoto: null,
  links: [],
  completa: false,
}

function mount(path = '/io') {
  const root = createRootRoute({ component: () => <Outlet /> })
  const io = createRoute({ getParentRoute: () => root, path: '/io', component: () => <Outlet /> })
  const index = createRoute({
    getParentRoute: () => io,
    path: '/',
    component: Area,
    validateSearch: (search: Record<string, unknown>): { negato?: true } => ({
      negato: search.negato === true || search.negato === 'true' ? true : undefined,
    }),
  })
  const modifica = createRoute({ getParentRoute: () => io, path: '/modifica', component: () => <h1>Modifica</h1> })
  const router = createRouter({
    routeTree: root.addChildren([io.addChildren([index, modifica])]),
    history: createMemoryHistory({ initialEntries: [path] }),
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

describe('/io, a card (REB-279: reads the merged `useMe`, gated on `ha_scheda`)', () => {
  it('shows the answers under the wizard’s questions, the CV and the two perks', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, PROFILE))
    mount()
    // The name is both the heading and the answer to the first question.
    expect(await screen.findAllByText('Ada Lovelace')).not.toHaveLength(0)
    expect(screen.getByText('Come ti chiami?')).toBeInTheDocument()
    expect(screen.getByText('450.00 € / giorno')).toBeInTheDocument()
    expect(screen.getByText('Ibrido')).toBeInTheDocument()
    expect(screen.getByText('ada@studio.it')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ada CV\.pdf/ })).toHaveAttribute('href', '/api/hub/me/cv')
    expect(screen.getByRole('link', { name: /Apri PigroCRM/ })).toHaveAttribute(
      'href',
      'https://pigro.letsrebase.com/app/registrati',
    )
    expect(screen.getByRole('link', { name: /Scarica la guida/ })).toHaveAttribute(
      'href',
      '/api/hub/me/guida',
    )
    expect(screen.getByText('PDF, 6 pagine, 48 KB.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Modifica' })).toHaveAttribute('href', '/io/modifica')
    // A complete card gets no reminder, and no access-rule banner either.
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByText('Nessun CV')).toBeNull()
  })

  it('asks the person to complete a card the admin wrote, and shows no CV link', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, INCOMPLETE))
    mount()
    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('La tua scheda è incompleta.')
    expect(within(notice).getByRole('link', { name: 'Completa la scheda' })).toHaveAttribute('href', '/io/modifica')
    expect(screen.getByText('Nessun CV')).toBeInTheDocument()
    expect(screen.getAllByRole('link').some((link) => link.getAttribute('href') === '/api/hub/me/cv')).toBe(false)
    // The unanswered questions read as dashes, not as a crash.
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3)
  })

  it('counts the guide on the click and leaves the download to the link', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, PROFILE))
    mount()
    const link = await screen.findByRole('link', { name: /Scarica la guida/ })
    // jsdom cannot navigate; stopping the default here does not stop React's own handler.
    link.addEventListener('click', (event) => event.preventDefault())
    await userEvent.setup().click(link)
    expect(capture).toHaveBeenCalledWith('guida_scaricata')
    expect(link).toHaveAttribute('href', '/api/hub/me/guida')
  })
})

describe('/io, no card (REB-279: a card-less admin reads name, email and role, not null fields)', () => {
  it('shows no wizard-shaped section, no Modifica link, and the role instead', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, CARDLESS_ADMIN))
    mount()
    expect(await screen.findByRole('heading', { name: 'Ivan Fiore' })).toBeInTheDocument()
    expect(screen.getByText('ivan@rebase.it')).toBeInTheDocument()
    expect(screen.getByText('Amministratore')).toBeInTheDocument()
    expect(screen.queryByText('Come ti chiami?')).toBeNull()
    expect(screen.queryByRole('link', { name: 'Modifica' })).toBeNull()
    expect(screen.queryByText('Nessun CV')).toBeNull()
    // The perks stay unconditional even with no card.
    expect(screen.getByRole('link', { name: /Apri PigroCRM/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Scarica la guida/ })).toBeInTheDocument()
  })
})

describe('/io?negato=true (REB-279: AdminGuard bounces a signed-in non-admin here)', () => {
  it('shows a sentence instead of a blank screen or a raw refusal', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, PROFILE))
    mount('/io?negato=true')
    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('riservata a chi amministra')
  })

  it('says nothing extra without the flag', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, PROFILE))
    mount('/io')
    await screen.findAllByText('Ada Lovelace')
    expect(screen.queryByRole('status')).toBeNull()
  })
})
