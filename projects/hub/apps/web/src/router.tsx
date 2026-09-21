import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from '@tanstack/react-router'
import type { CompaniesFilters, Remoto, TalentiFilters } from '@/lib/api'
import { Shell } from '@/components/Shell'
import { Chooser } from '@/pages/Chooser'
import { CompanyWizard } from '@/pages/CompanyWizard'
import { FreelancerWizard } from '@/pages/FreelancerWizard'
import { SignedInLayout } from '@/pages/SignedInLayout'
import { AdminAccessi } from '@/pages/admin/Accessi'
import { AdminAdmins } from '@/pages/admin/Admins'
import { AdminAgenti } from '@/pages/admin/Agenti'
import { AdminGuard } from '@/pages/admin/AdminGuard'
import { AdminGuida } from '@/pages/admin/Guida'
import { AdminPigro } from '@/pages/admin/Pigro'
import { Thanks } from '@/pages/Thanks'
import {
  AdminCompanies,
  AdminCompanyDetail,
  AdminFreelancerDetail,
  AdminTalenti,
  AdminTalentoLead,
} from '@/pages/admin/lists'
import { Accedi } from '@/pages/member/Accedi'
import { Area } from '@/pages/member/Area'
import { Entra } from '@/pages/member/Entra'
import { Modifica } from '@/pages/member/Modifica'
import { ModificaAzienda } from '@/pages/member/ModificaAzienda'

/** A present, non-empty string out of `Record<string, unknown>`'s raw search params,
 *  or `undefined` -- the shape every optional filter on `/admin/talenti` and
 *  `/admin/aziende` shares (REB-286), the same narrowing `grazie`'s `chi` and
 *  `entra`'s `t` do below for their own single required param.
 *
 *  The router's default `parseSearch` runs `JSON.parse` on every raw query-string
 *  value before `validateSearch` sees it, so a purely numeric value in the URL
 *  (`?tariffa_min=50`) or a bare `true`/`false` arrives as that JS type, not a
 *  string -- on first load, a reload, a shared link, or back/forward, never on an
 *  in-app `navigate()`, which is why this only shows up outside the tab that set it.
 *  Coerced back to the string it was in the URL, the same treatment the `has_cv`/
 *  `con_accessi` booleans below already needed for the same reason. */
export function strParam(value: unknown): string | undefined {
  if (typeof value === 'string') return value !== '' ? value : undefined
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return undefined
}

/**
 * The route tree, in code: this many screens is not enough to want a file-based router and
 * a generated tree beside it. The public pages sit in the `Shell`, the chooser alone in
 * a `Shell` without its panel (ORB-128); every signed-in route -- the member area and the
 * admin area alike -- shares one guard and one frame, `SignedInLayout` (REB-279, merging
 * the old `AdminLayout` and `MemberGuard`). `/admin/*` carries one more guard of its own,
 * `AdminGuard`, gating on role rather than on being signed in at all: a signed-in
 * non-admin at `/admin/*` lands on `/io` with a sentence, never on a blank frame
 * (REB-106) or a login form.
 */
const root = createRootRoute({ component: () => <Outlet /> })

const publicLayout = createRoute({
  getParentRoute: () => root,
  id: 'public',
  component: () => (
    <Shell>
      <Outlet />
    </Shell>
  ),
})

const bareLayout = createRoute({
  getParentRoute: () => root,
  id: 'bare',
  component: () => (
    <Shell panel={false}>
      <Outlet />
    </Shell>
  ),
})

const chooser = createRoute({ getParentRoute: () => bareLayout, path: '/', component: Chooser })
const freelance = createRoute({
  getParentRoute: () => publicLayout,
  path: '/freelance',
  component: FreelancerWizard,
})
const aziende = createRoute({
  getParentRoute: () => publicLayout,
  path: '/aziende',
  component: CompanyWizard,
})
const grazie = createRoute({
  getParentRoute: () => publicLayout,
  path: '/grazie',
  validateSearch: (search: Record<string, unknown>): { chi: 'freelance' | 'azienda' } => ({
    chi: search.chi === 'azienda' ? 'azienda' : 'freelance',
  }),
  component: Thanks,
})
const accedi = createRoute({ getParentRoute: () => publicLayout, path: '/accedi', component: Accedi })
const entra = createRoute({
  getParentRoute: () => publicLayout,
  path: '/entra',
  validateSearch: (search: Record<string, unknown>): { t: string } => ({
    t: typeof search.t === 'string' ? search.t : '',
  }),
  component: Entra,
})

const signedInLayout = createRoute({
  getParentRoute: () => root,
  id: 'signedIn',
  component: SignedInLayout,
})

const io = createRoute({ getParentRoute: () => signedInLayout, path: '/io', component: () => <Outlet /> })
const ioIndex = createRoute({
  getParentRoute: () => io,
  path: '/',
  component: Area,
  // Set by `AdminGuard` when a signed-in non-admin is bounced off `/admin/*`
  // (REB-279's own access rule): `Area` reads it to say why, rather than a blank
  // screen or a raw 403.
  validateSearch: (search: Record<string, unknown>): { negato?: true } => ({
    negato: search.negato === true || search.negato === 'true' ? true : undefined,
  }),
})
const ioModifica = createRoute({ getParentRoute: () => io, path: '/modifica', component: Modifica })
const ioModificaAzienda = createRoute({
  getParentRoute: () => io,
  path: '/modifica-azienda',
  component: ModificaAzienda,
})

const adminArea = createRoute({ getParentRoute: () => signedInLayout, path: '/admin', component: AdminGuard })
const adminTalenti = createRoute({
  getParentRoute: () => adminArea,
  path: '/talenti',
  component: AdminTalenti,
  // REB-286: every filter and the search box live here too, so a reload or a shared
  // link reproduces the exact list -- `q` included even though the debounce that
  // settles it lives in `AdminTalenti` itself, not here.
  validateSearch: (search: Record<string, unknown>): TalentiFilters => ({
    stato: strParam(search.stato),
    q: strParam(search.q),
    posizione: strParam(search.posizione),
    remoto:
      search.remoto === 'remoto' || search.remoto === 'ibrido' || search.remoto === 'in_sede'
        ? (search.remoto as Remoto)
        : undefined,
    tariffa_min: strParam(search.tariffa_min),
    tariffa_max: strParam(search.tariffa_max),
    origine: strParam(search.origine),
    utm_source: strParam(search.utm_source),
    has_cv: search.has_cv === true || search.has_cv === 'true' ? true : search.has_cv === false || search.has_cv === 'false' ? false : undefined,
    con_accessi:
      search.con_accessi === true || search.con_accessi === 'true'
        ? true
        : search.con_accessi === false || search.con_accessi === 'false'
          ? false
          : undefined,
    creato_da: strParam(search.creato_da),
    creato_a: strParam(search.creato_a),
  }),
})
const adminTalentoLead = createRoute({
  getParentRoute: () => adminArea,
  path: '/talenti/$id',
  component: AdminTalentoLead,
})
const adminFreelanceDetail = createRoute({
  getParentRoute: () => adminArea,
  path: '/freelance/$id',
  component: AdminFreelancerDetail,
})
// The website's footer links to /hub/admin/freelance (ORB-106: the hub router has no
// index route under /admin, so a signed-in admin sent to a bare /admin would see the
// frame with an empty panel). Talenti replaced the list this used to be (REB-283); the
// redirect keeps that one documented door open rather than 404ing it.
const adminFreelanceRedirect = createRoute({
  getParentRoute: () => adminArea,
  path: '/freelance',
  beforeLoad: () => {
    throw redirect({ to: '/admin/talenti' })
  },
})
const adminAziende = createRoute({
  getParentRoute: () => adminArea,
  path: '/aziende',
  component: AdminCompanies,
  validateSearch: (search: Record<string, unknown>): CompaniesFilters => ({
    stato: strParam(search.stato),
    q: strParam(search.q),
    budget_min: strParam(search.budget_min),
    budget_max: strParam(search.budget_max),
    periodo_da: strParam(search.periodo_da),
    origine: strParam(search.origine),
    creato_da: strParam(search.creato_da),
    creato_a: strParam(search.creato_a),
  }),
})
const adminAziendeDetail = createRoute({
  getParentRoute: () => adminArea,
  path: '/aziende/$id',
  component: AdminCompanyDetail,
})
const adminPigro = createRoute({ getParentRoute: () => adminArea, path: '/pigro', component: AdminPigro })
const adminGuida = createRoute({ getParentRoute: () => adminArea, path: '/guida', component: AdminGuida })
const adminAccessi = createRoute({ getParentRoute: () => adminArea, path: '/accessi', component: AdminAccessi })
const adminAmministratori = createRoute({
  getParentRoute: () => adminArea,
  path: '/amministratori',
  component: AdminAdmins,
})
const adminAgenti = createRoute({ getParentRoute: () => adminArea, path: '/agenti', component: AdminAgenti })

const routeTree = root.addChildren([
  bareLayout.addChildren([chooser]),
  publicLayout.addChildren([freelance, aziende, grazie, accedi, entra]),
  signedInLayout.addChildren([
    io.addChildren([ioIndex, ioModifica, ioModificaAzienda]),
    adminArea.addChildren([
      adminTalenti,
      adminTalentoLead,
      adminFreelanceDetail,
      adminFreelanceRedirect,
      adminAziende,
      adminAziendeDetail,
      adminPigro,
      adminGuida,
      adminAccessi,
      adminAmministratori,
      adminAgenti,
    ]),
  ]),
])

export const router = createRouter({ routeTree, basepath: '/hub' })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
