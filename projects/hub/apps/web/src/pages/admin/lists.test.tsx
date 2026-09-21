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
import { AdminFreelancerDetail, AdminTalenti, AdminTalentoLead } from './lists'

function answer(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** A card the admin wrote from a signup (ORB-155): no CV, no rate, no position, no
 *  remote preference, and the attribution that says so. */
const INCOMPLETE = {
  id: 'f1',
  nome: 'Ada',
  cognome: 'Lovelace',
  email: 'ada@studio.it',
  linkedin_url: 'https://www.linkedin.com/in/ada',
  cv_filename: null,
  cv_size: null,
  tariffa_giornaliera: null,
  posizione: null,
  remoto: null,
  links: ['https://github.com/ada'],
  stato: 'nuovo',
  note: null,
  utm_source: 'linkedin',
  utm_campaign: null,
  created_at: '2026-09-10T10:00:00Z',
  compilata_da: 'admin',
  completa: false,
  commenti: [],
  accessi: 0,
  provenienza: 'form',
  ultimo_accesso: null,
  iscrizione_utm: null,
  ultimi_accessi: [],
  ultimi_download_guida: [],
  pigro_slug: null,
}

const COMPLETE = {
  ...INCOMPLETE,
  id: 'f2',
  nome: 'Grace',
  cognome: 'Hopper',
  email: 'grace@studio.it',
  cv_filename: 'Grace CV.pdf',
  cv_size: 2048,
  tariffa_giornaliera: '500.00',
  posizione: 'CTO',
  remoto: 'remoto',
  compilata_da: 'persona',
  completa: true,
  accessi: 3,
  provenienza: 'landing',
  ultimo_accesso: '2026-09-11T12:04:00Z',
}

/** A card in `talenti` (REB-282/283): a freelancer already written, `origine` naming
 *  the wizard the person filled in themselves. */
const CARD_TALENTO = {
  id: 'f1',
  nome: 'Ada',
  cognome: 'Lovelace',
  email: 'ada@studio.it',
  linkedin_url: 'https://www.linkedin.com/in/ada',
  stato: 'nuovo',
  origine: 'wizard',
  utm_source: 'linkedin',
  created_at: '2026-09-10T10:00:00Z',
}

/** A bare sign-up in `talenti` (ORB-163): `stato` `lead`, no card behind it yet. */
const LEAD_TALENTO = {
  id: 's2',
  nome: 'Bob',
  cognome: 'Ross',
  email: 'bob@example.org',
  linkedin_url: 'https://www.linkedin.com/in/bob',
  stato: 'lead',
  origine: 'form',
  utm_source: 'newsletter',
  created_at: '2026-09-08T10:00:00Z',
}

/** The admin routes these pages sit on, without the frame and its guard: the pages
 *  read `useParams` and render `Link`s, so a router has to be there. The pathless
 *  `signedIn` id mirrors the real tree (REB-279's `SignedInLayout`), since
 *  `AdminFreelancerDetail`'s and `AdminTalentoLead`'s own `useParams({ from })` name
 *  that full route id. */
function mount(path: string) {
  const root = createRootRoute({ component: () => <Outlet /> })
  const signedIn = createRoute({ getParentRoute: () => root, id: 'signedIn', component: () => <Outlet /> })
  const talenti = createRoute({ getParentRoute: () => signedIn, path: '/admin/talenti', component: AdminTalenti })
  const talentoLead = createRoute({
    getParentRoute: () => signedIn,
    path: '/admin/talenti/$id',
    component: AdminTalentoLead,
  })
  const freelanceDetail = createRoute({
    getParentRoute: () => signedIn,
    path: '/admin/freelance/$id',
    component: AdminFreelancerDetail,
  })
  const router = createRouter({
    routeTree: root.addChildren([signedIn.addChildren([talenti, talentoLead, freelanceDetail])]),
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

/** The cell under a given column header, so a «—» is checked where it is expected and
 *  not anywhere on the row. */
function cellUnder(row: HTMLElement, header: string): HTMLElement {
  const table = row.closest('table')!
  const headers = within(table).getAllByRole('columnheader').map((cell) => cell.textContent)
  const index = headers.indexOf(header)
  expect(index).toBeGreaterThanOrEqual(0)
  return within(row).getAllByRole('cell')[index]!
}

afterEach(() => vi.restoreAllMocks())

describe('the Talenti list (REB-282/283)', () => {
  it('lists a card and a lead together, each with its own state and origin, and links to the right page', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      answer(200, { totale: 2, items: [CARD_TALENTO, LEAD_TALENTO], per_stato: { nuovo: 1, lead: 1 } }),
    )
    mount('/admin/talenti')

    const ada = (await screen.findByText('ada@studio.it')).closest('tr')!
    expect(within(cellUnder(ada, 'Stato')).getByText('Nuovo')).toBeInTheDocument()
    expect(cellUnder(ada, 'Provenienza')).toHaveTextContent('wizard')
    const adaLink = within(ada).getByRole('link')
    expect(adaLink.getAttribute('href')).toMatch(/\/admin\/freelance\/f1$/)

    const bob = screen.getByText('bob@example.org').closest('tr')!
    expect(within(cellUnder(bob, 'Stato')).getByText('Lead')).toBeInTheDocument()
    expect(cellUnder(bob, 'Provenienza')).toHaveTextContent('form')
    const bobLink = within(bob).getByRole('link')
    expect(bobLink.getAttribute('href')).toMatch(/\/admin\/talenti\/s2$/)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('2')
  })

  it('filters by state through the same pills as before, «Lead» included', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, { totale: 0, items: [], per_stato: {} }))
    mount('/admin/talenti')
    await screen.findByRole('heading', { name: 'Talenti' })
    expect(screen.getByRole('button', { name: 'Nuovo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lead' })).toBeInTheDocument()
  })
})

describe('a lead offers to draft a card in place (ORB-155, REB-283)', () => {
  it('shows what the sign-up says, drafts a card from the given sources, and opens the new card', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'POST') {
        expect(url).toBe('/api/hub/signups/s2/scheda')
        expect(JSON.parse(init.body as string)).toEqual({
          nome: 'Bob',
          cognome: 'Ross',
          linkedin_url: 'https://www.linkedin.com/in/bob',
          links: [],
          fonti: ['https://bob.dev'],
        })
        return answer(201, { ...INCOMPLETE, id: 'f9', nome: 'Bob', cognome: 'Ross' })
      }
      if (url === '/api/hub/freelancers/f9') {
        return answer(200, { ...INCOMPLETE, id: 'f9', nome: 'Bob', cognome: 'Ross' })
      }
      return answer(200, { totale: 1, items: [LEAD_TALENTO], per_stato: { lead: 1 } })
    })
    mount('/admin/talenti/s2')

    await screen.findByRole('heading', { name: 'Bob Ross' })
    expect(screen.getByDisplayValue('Bob')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Ross')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Fonti'), 'https://bob.dev')
    await userEvent.click(screen.getByRole('button', { name: 'Crea scheda' }))

    // Landing on the existing freelancer detail (not rewritten here, REB-284's job):
    // its own ownership sentence for a card an admin wrote is proof the redirect worked,
    // and the GET above proves the redirect's $id is the card the POST actually created.
    expect(await screen.findByText('scritta dall’admin, da completare')).toBeInTheDocument()
    expect(spy).toHaveBeenCalled()
  })

  it('refuses without at least one source, since a card written from research needs one', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      answer(200, { totale: 1, items: [LEAD_TALENTO], per_stato: { lead: 1 } }),
    )
    mount('/admin/talenti/s2')
    await screen.findByRole('heading', { name: 'Bob Ross' })
    expect(screen.getByLabelText('Fonti')).toBeRequired()
  })
})

describe('the freelancer detail', () => {
  it('shows an incomplete card without a CV link and says the admin wrote it', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, INCOMPLETE))
    mount('/admin/freelance/f1')
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    expect(spy.mock.calls[0]![0]).toBe('/api/hub/freelancers/f1')
    expect(screen.queryByRole('link', { name: /CV/ })).toBeNull()
    expect(screen.getByText('Da completare')).toBeInTheDocument()
    expect(screen.getByText('scritta dall’admin, da completare')).toBeInTheDocument()
    expect(screen.getByText('Mai entrato')).toBeInTheDocument()
    // The three answers the person has not given yet read as dashes, not as a crash.
    const rows = screen.getAllByRole('definition')
    expect(rows.filter((row) => row.textContent === '—').length).toBeGreaterThanOrEqual(3)
  })

  it('shows a complete card with its CV and says the person filled it in', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, COMPLETE))
    mount('/admin/freelance/f2')
    await screen.findByRole('heading', { name: 'Grace Hopper' })
    expect(screen.getByRole('link', { name: /CV/ })).toHaveAttribute('href', '/api/hub/freelancers/f2/cv')
    expect(screen.queryByText('Da completare')).toBeNull()
    expect(screen.getByText('compilata dalla persona')).toBeInTheDocument()
    expect(screen.getByText('Da remoto')).toBeInTheDocument()
    expect(screen.getByText(/^3 · ultimo 11 set 2026/)).toBeInTheDocument()
  })
})

describe('the enriched detail: sign-up, logins, downloads, Pigro space (REB-284)', () => {
  const ENRICHED = {
    ...COMPLETE,
    iscrizione_utm: {
      utm_source: 'newsletter',
      utm_medium: 'email',
      utm_campaign: 'autunno-2026',
      utm_content: null,
      utm_term: null,
      utm_id: null,
    },
    ultimi_accessi: [
      { id: 'l1', logged_at: '2026-09-12T09:00:00Z' },
      { id: 'l2', logged_at: '2026-09-11T09:00:00Z' },
    ],
    ultimi_download_guida: [{ id: 'd1', downloaded_at: '2026-09-10T09:00:00Z' }],
    pigro_slug: 'studio-grace',
  }

  it('shows the sign-up utm, the recent logins and downloads, and the Pigro slug, in order', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(answer(200, ENRICHED))
    mount('/admin/freelance/f2')
    await screen.findByRole('heading', { name: 'Grace Hopper' })
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual([
      'Iscrizione alla newsletter',
      'Ultimi accessi',
      'Download della guida',
      'Spazio PigroCRM',
      'Commenti',
    ])
    expect(screen.getByText('newsletter')).toBeInTheDocument()
    expect(screen.getByText('email')).toBeInTheDocument()
    expect(screen.getByText('autunno-2026')).toBeInTheDocument()
    expect(screen.getByText('studio-grace')).toBeInTheDocument()
  })

  it('shows sensible empty values with none of the four sources, not a crash', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      answer(200, {
        ...INCOMPLETE,
        iscrizione_utm: null,
        ultimi_accessi: [],
        ultimi_download_guida: [],
        pigro_slug: null,
      }),
    )
    mount('/admin/freelance/f1')
    await screen.findByRole('heading', { name: 'Ada Lovelace' })
    expect(screen.getByText('Nessuna iscrizione con questo indirizzo.')).toBeInTheDocument()
    expect(screen.getByText('Non è mai entrata.')).toBeInTheDocument()
    expect(screen.getByText('Non ha scaricato la guida.')).toBeInTheDocument()
    // No slug at all: the section does not render rather than showing an empty one.
    expect(screen.queryByText('Spazio PigroCRM')).toBeNull()
  })

  it('keeps the enriched sections after saving a state change from the plain PATCH response', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    spy.mockResolvedValueOnce(answer(200, ENRICHED))
    mount('/admin/freelance/f2')
    await screen.findByRole('heading', { name: 'Grace Hopper' })
    expect(screen.getByText('studio-grace')).toBeInTheDocument()

    // `PATCH /freelancers/{id}` answers a plain `FreelancerRead`: none of REB-284's
    // keys even exist on the body, since only `get`'s response model carries them.
    const plainCard: Record<string, unknown> = { ...ENRICHED, stato: 'contattato' }
    delete plainCard.iscrizione_utm
    delete plainCard.ultimi_accessi
    delete plainCard.ultimi_download_guida
    delete plainCard.pigro_slug
    spy.mockResolvedValueOnce(answer(200, plainCard))
    await userEvent.click(screen.getByRole('button', { name: 'Contattato' }))
    await userEvent.click(screen.getByRole('button', { name: 'Salva' }))
    const banner = await screen.findByRole('banner')
    await within(banner).findByText('Contattato')
    // The save must merge onto the cached detail, not replace it: the Pigro slug and
    // the other REB-284 sections the PATCH never answers stay on the page.
    expect(screen.getByText('studio-grace')).toBeInTheDocument()
    expect(screen.getByText('newsletter')).toBeInTheDocument()
  })
})
