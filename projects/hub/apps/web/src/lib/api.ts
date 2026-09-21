/**
 * The hub's HTTP client: plain `fetch`, same origin, cookies included. The API is a
 * handful of routes and three shapes, so a generated client would be more machinery
 * than code.
 *
 * Every failure becomes an `ApiError` carrying the status and, for a 422, the field
 * names FastAPI put in `detail[].loc`, which is what a wizard needs to point at the
 * right question rather than blame the whole form.
 */

import { linkedinProfile } from './linkedin'
import type { Utm } from './utm'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly fields: string[] = [],
  ) {
    super(message)
  }
}

interface ValidationItem {
  loc?: unknown[]
  msg?: string
}

async function fail(response: Response): Promise<never> {
  let detail: unknown = null
  try {
    detail = (await response.json())?.detail
  } catch {
    detail = null
  }
  if (Array.isArray(detail)) {
    const items = detail as ValidationItem[]
    const fields = items.map((item) => String(item.loc?.at(-1) ?? '')).filter(Boolean)
    const message = items.map((item) => item.msg).filter(Boolean).join(' · ') || 'Dati non validi.'
    throw new ApiError(response.status, message, fields)
  }
  if (response.status === 429) {
    throw new ApiError(429, 'Troppe richieste da qui. Riprova tra un minuto.')
  }
  throw new ApiError(
    response.status,
    typeof detail === 'string' ? detail : `Qualcosa è andato storto (${response.status}).`,
  )
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) await fail(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

// ---- the two wizards ------------------------------------------------------------------

export type Remoto = 'remoto' | 'ibrido' | 'in_sede'

export interface FreelancerApplication {
  nome: string
  cognome: string
  email: string
  linkedin_url: string
  tariffa_giornaliera: string
  posizione: string
  remoto: Remoto | ''
  links: string[]
  cv: File | null
}

/** Multipart, because the CV is a file. Empty optional fields are left out rather than
 *  sent as `""`, which the API would try to validate as a value. */
export function applyAsFreelancer(
  data: FreelancerApplication,
  utm: Utm,
  distinctId: string | null = null,
): Promise<{ ok: true }> {
  const form = new FormData()
  // The browser's PostHog id, when the page is measured: the API sends the completion
  // event itself (REB-215), and this is what puts it on the same person as the steps.
  if (distinctId) form.set('distinct_id', distinctId)
  form.set('nome', data.nome)
  form.set('cognome', data.cognome)
  form.set('email', data.email)
  form.set('tariffa_giornaliera', data.tariffa_giornaliera)
  form.set('posizione', data.posizione)
  form.set('remoto', data.remoto)
  const linkedin = linkedinProfile(data.linkedin_url)
  if (linkedin) form.set('linkedin_url', linkedin)
  for (const link of data.links) if (link.trim()) form.append('links', link.trim())
  for (const [key, value] of Object.entries(utm)) if (value) form.set(key, value)
  if (data.cv) form.set('cv', data.cv, data.cv.name)
  return request('/api/hub/freelancers', { method: 'POST', body: form })
}

export interface CompanyRequest {
  nome_azienda: string
  referente_nome: string
  referente_cognome: string
  email: string
  progetto: string
  periodo_da: string
  durata: string
  budget_giornaliero: string
}

export function requestPeople(
  data: CompanyRequest,
  utm: Utm,
  distinctId: string | null = null,
): Promise<{ ok: true }> {
  return request(
    '/api/hub/companies',
    json({
      ...data,
      utm: Object.keys(utm).length ? utm : null,
      ...(distinctId ? { distinct_id: distinctId } : {}),
    }),
  )
}

// ---- the admin area -------------------------------------------------------------------

export type Role = 'member' | 'admin'

export interface Admin {
  id: string
  email: string
  nome: string
  attivo: boolean
  created_at: string
}

/** What `POST /admins/promote` sends: an email, and `nome`/`cognome` for an address
 *  with no `users` row yet -- ignored, harmlessly, when one already exists. */
export interface PromoteRequest {
  email: string
  nome?: string
  cognome?: string
}

export interface Freelancer {
  id: string
  nome: string
  cognome: string
  email: string
  linkedin_url: string | null
  /** Null on a card an admin wrote from a signup, until the person adds them (ORB-155). */
  cv_filename: string | null
  cv_size: number | null
  tariffa_giornaliera: string | null
  posizione: string | null
  remoto: Remoto | null
  links: string[]
  stato: 'nuovo' | 'contattato' | 'attivo' | 'scartato'
  note: string | null
  /** The page of the site the person started from, `home` or `pigrocrm` (ORB-167). */
  origine: string | null
  utm_source: string | null
  utm_campaign: string | null
  created_at: string
  /** Who wrote the answers last: the person, through the wizard or the member area, or
   *  an admin from research. */
  compilata_da: 'persona' | 'admin'
  /** CV, rate, position and remote preference all present. */
  completa: boolean
  /** The thread, newest first. The detail carries it; the list leaves it empty. */
  commenti: Comment[]
  /** How many times the person came in through the magic link (ORB-158). */
  accessi: number
  /** Where the lead came from (ORB-161): «form» when the address is also among the
   *  signups («Iscrizioni»), «landing» otherwise. */
  provenienza: 'form' | 'landing'
  /** When they last did, null if never. */
  ultimo_accesso: string | null
}

export interface Company {
  id: string
  nome_azienda: string
  referente: string
  email: string
  progetto: string
  periodo_da: string
  durata: string
  budget_giornaliero: string
  stato: 'nuovo' | 'contattato' | 'in_corso' | 'chiuso'
  note: string | null
  /** The page of the site the person started from, `home` or `pigrocrm` (ORB-167). */
  origine: string | null
  utm_source: string | null
  created_at: string
  commenti: Comment[]
}

/** One remark in a row's thread: appended, signed and dated, never edited. */
export interface Comment {
  id: string
  entity_type: 'freelancer' | 'company'
  entity_id: string
  testo: string
  autore: string
  created_at: string
}

/** The two rows a thread can hang on, as the API paths name them. */
export type CommentKind = 'freelancers' | 'companies'

/** One space of PigroCRM as the registry knows it, plus the hub member who opened it
 *  when the address is one the wizard has seen (ORB-142). */
export interface PigroSpace {
  slug: string
  owner_email: string
  created_at: string
  url: string
  membro: { id: string; nome: string; cognome: string } | null
}

/** The guide's numbers for the admin area (ORB-156), as `GET /api/hub/perks/guida` answers. */
export interface GuideStats {
  totale: number
  membri: number
  membri_totali: number
  ultimi_7_giorni: number
  recenti: GuideDownload[]
}

export interface GuideDownload {
  id: string
  freelancer_id: string
  nome: string
  cognome: string
  email: string
  downloaded_at: string
}

/** The logins for the admin area (ORB-158), as `GET /api/hub/logins` answers. */
export interface LoginStats {
  totale: number
  membri: number
  membri_totali: number
  ultimi_7_giorni: number
  recenti: LoginRead[]
}

export interface LoginRead {
  id: string
  freelancer_id: string
  nome: string
  cognome: string
  email: string
  logged_at: string
}

/** One row of `talenti` (REB-282/283): every freelancer card and every bare sign-up
 *  as one row, `stato` `lead` for the bare ones and the freelancer's own state
 *  otherwise, as `GET /api/hub/talenti` answers -- the single list that replaced
 *  «Developer e CTO» and «Iscrizioni». `origine` names how the row came to be:
 *  `form` for a bare sign-up, `wizard` for a card the person filled in themselves,
 *  `admin` for one an admin drafted from research (ORB-155). */
export interface Talento {
  id: string
  nome: string | null
  cognome: string | null
  email: string
  linkedin_url: string | null
  stato: string
  origine: 'form' | 'wizard' | 'admin'
  utm_source: string | null
  created_at: string
}

/** What an admin found about a signup on the public web (ORB-155): a name, maybe a
 *  LinkedIn profile, a position, some links, and at least one source, since a card
 *  written from research with no source is a card nobody can check. The body
 *  `POST /api/hub/signups/{id}/scheda` expects -- the same `draft_from_signup` the
 *  MCP tool `create_freelancer_from_signup` calls. */
export interface FreelancerDraft {
  nome: string
  cognome: string
  linkedin_url?: string
  posizione?: string
  tariffa_giornaliera?: string
  remoto?: Remoto
  links?: string[]
  fonti: string[]
}

/** A personal token of the admin, as `GET /api/hub/tokens` lists it (REB-213): never the value. */
export interface AdminToken {
  id: string
  nome: string
  prefix: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

/** The `POST` answer: the one place the value appears, shown once. */
export interface CreatedToken extends AdminToken {
  token: string
}

export const admin = {
  freelancer: (id: string) => request<Freelancer>(`/api/hub/freelancers/${id}`),
  cvUrl: (id: string) => `/api/hub/freelancers/${id}/cv`,
  moveFreelancer: (id: string, stato: string, note: string | null) =>
    request<Freelancer>(`/api/hub/freelancers/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stato, note }),
    }),
  companies: (stato?: string) =>
    request<{ totale: number; items: Company[] }>(
      `/api/hub/companies?limit=500${stato ? `&stato=${encodeURIComponent(stato)}` : ''}`,
    ),
  company: (id: string) => request<Company>(`/api/hub/companies/${id}`),
  moveCompany: (id: string, stato: string, note: string | null) =>
    request<Company>(`/api/hub/companies/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stato, note }),
    }),
  /** Every card and every bare sign-up as one list (REB-282/283), `stato` `lead` for
   *  the bare ones alone -- the read model «Talenti» replaced «Developer e CTO» and
   *  «Iscrizioni» with. */
  talenti: (stato?: string) =>
    request<{ totale: number; items: Talento[]; per_stato: Record<string, number> }>(
      `/api/hub/talenti?limit=500${stato ? `&stato=${encodeURIComponent(stato)}` : ''}`,
    ),
  /** Drafts a card from a bare sign-up in place (ORB-155): the same `draft_from_signup`
   *  the MCP tool `create_freelancer_from_signup` calls, here behind the admin's
   *  cookie. 201 with the new (incomplete) card, or a 422 naming `email` when the
   *  person has already filled their own. */
  draftFromSignup: (signupId: string, data: FreelancerDraft) =>
    request<Freelancer>(`/api/hub/signups/${signupId}/scheda`, json(data)),
  /** PigroCRM's spaces, read by the hub's API with the token it holds: the browser
   *  never talks to the CRM (ORB-142). A 503 carries the sentence the page shows. */
  pigroSpaces: () => request<{ totale: number; items: PigroSpace[] }>('/api/hub/pigro/istanze'),
  /** How the guide is doing: downloads, the members behind them, the latest (ORB-156). */
  guideStats: () => request<GuideStats>('/api/hub/perks/guida'),
  /** Who comes back in: logins, the members behind them, the latest (ORB-158). */
  loginStats: () => request<LoginStats>('/api/hub/logins'),
  /** Who reads this area, oldest first, and one more of them (ORB-123). */
  admins: () => request<Admin[]>('/api/hub/admins'),
  /** Promotes whatever `users` row already answers to this address, or creates a bare
   *  one from `nome`/`cognome` when none exists yet (REB-279, no password anywhere). */
  promote: (data: PromoteRequest) => request<Admin>('/api/hub/admins/promote', json(data)),
  /** Sets `role = 'member'`, fully reversible since nothing is deleted. */
  demote: (id: string) => request<Admin>(`/api/hub/admins/${id}/demote`, { method: 'POST' }),
  /** The admin's own tokens for agents, newest first, revoked ones included (REB-213). */
  tokens: () => request<AdminToken[]>('/api/hub/tokens'),
  createToken: (nome: string) => request<CreatedToken>('/api/hub/tokens', json({ nome })),
  revokeToken: (id: string) => request<void>(`/api/hub/tokens/${id}`, { method: 'DELETE' }),
  comments: (kind: CommentKind, id: string) =>
    request<Comment[]>(`/api/hub/${kind}/${id}/comments`),
  /** The author is the session's, so the body is the text alone. */
  addComment: (kind: CommentKind, id: string, testo: string) =>
    request<Comment>(`/api/hub/${kind}/${id}/comments`, json({ testo })),
}

// ---- whoever is signed in --------------------------------------------------------------

/** Whoever `orbiters_user` resolves to, member or admin (REB-278/279, replacing
 *  `MemberProfile`): a `users` row is not necessarily an applicant with a card any
 *  more, so `ha_scheda` says whether one exists, and the seven card fields answer
 *  blank -- `null`, `false`, `[]` -- when it does not, the shape a signed-in admin
 *  with no card gets. `ha_azienda` and the four request fields mirror `ha_scheda`'s
 *  own shape for a company contact's most recent request (REB-314): a person can
 *  carry both, one, or neither. */
export interface Me {
  id: string
  nome: string
  cognome: string
  email: string
  linkedin_url: string | null
  role: Role
  created_at: string
  updated_at: string
  ha_scheda: boolean
  cv_filename: string | null
  cv_size: number | null
  tariffa_giornaliera: string | null
  posizione: string | null
  remoto: Remoto | null
  links: string[]
  ha_azienda: boolean
  progetto: string | null
  periodo_da: string | null
  durata: string | null
  budget_giornaliero: string | null
  /** CV, rate, position and remote preference all present. Always `false` without a
   *  card (`ha_scheda`). */
  completa: boolean
}

/** The seven answers a member may change. The email is not among them. */
export interface MemberUpdate {
  nome: string
  cognome: string
  linkedin_url: string | null
  tariffa_giornaliera: string
  posizione: string
  remoto: Remoto
  links: string[]
}

/** The four answers a company contact may change about their most recent request
 *  (REB-314): never `stato`, `note` or the company's own identity. */
export interface CompanyUpdate {
  progetto: string
  periodo_da: string
  durata: string
  budget_giornaliero: string
}

export const member = {
  /** 202 whether the address is known or not; the page says one thing in both cases. */
  requestLink: (email: string) => request<{ ok: true }>('/api/hub/auth/link', json({ email })),
  enter: (token: string) => request<Me>('/api/hub/auth/enter', json({ token })),
  me: () => request<Me>('/api/hub/me'),
  update: (data: MemberUpdate) =>
    request<Me>('/api/hub/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  updateCompany: (data: CompanyUpdate) =>
    request<Me>('/api/hub/me/azienda', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  replaceCv: (file: File) => {
    const form = new FormData()
    form.set('cv', file, file.name)
    return request<Me>('/api/hub/me/cv', { method: 'PUT', body: form })
  },
  cvUrl: '/api/hub/me/cv',
  /** The guide, the community's second perk. A plain href rather than a fetch: the
   *  route answers with an attachment, and a session cookie travels with a navigation
   *  the same way it travels with a request. */
  guideUrl: '/api/hub/me/guida',
  logout: () => request<void>('/api/hub/me/logout', { method: 'POST' }),
}
