import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
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

const adminArea = createRoute({ getParentRoute: () => signedInLayout, path: '/admin', component: AdminGuard })
const adminTalenti = createRoute({
  getParentRoute: () => adminArea,
  path: '/talenti',
  component: AdminTalenti,
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
const adminAziende = createRoute({ getParentRoute: () => adminArea, path: '/aziende', component: AdminCompanies })
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
    io.addChildren([ioIndex, ioModifica]),
    adminArea.addChildren([
      adminTalenti,
      adminTalentoLead,
      adminFreelanceDetail,
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
