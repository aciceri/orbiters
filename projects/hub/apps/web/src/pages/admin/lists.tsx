import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { ArrowLeft, Download } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Badge } from '@rebase/ui/badge'
import { Button } from '@rebase/ui/button'
import { Input } from '@rebase/ui/input'
import { Label } from '@rebase/ui/label'
import { Textarea } from '@rebase/ui/textarea'
import {
  admin,
  ApiError,
  type Comment,
  type Company,
  type Freelancer,
  type FreelancerDraft,
  type Remoto,
  type Talento,
} from '@/lib/api'
import {
  COMPANY_STATES,
  FREELANCER_LIST_STATES,
  FREELANCER_STATES,
  REMOTO_LABELS,
  STATE_LABELS,
  formatBytes,
  formatDate,
  formatDateTime,
  formatEuro,
} from '@/lib/format'
import { cn } from '@rebase/ui/cn'
import { Comments } from './Comments'

const TONE: Record<string, string> = {
  nuovo: 'bg-[var(--color-royal-gold)]',
  lead: 'bg-muted',
  contattato: 'bg-muted-foreground',
  attivo: 'bg-foreground',
  in_corso: 'bg-foreground',
  scartato: 'bg-[var(--color-watermelon)]',
  chiuso: 'bg-muted-foreground',
}

function StatePill({ stato }: { stato: string }) {
  return (
    <Badge variant="pill" className="gap-1.5">
      <span aria-hidden="true" className={cn('size-1.5 rounded-full', TONE[stato] ?? 'bg-muted')} />
      {STATE_LABELS[stato] ?? stato}
    </Badge>
  )
}

/** Beside the state pill on a card that is missing the CV, the rate, the position or
 *  the remote preference. Either an admin wrote it from a signup and the person has not
 *  finished yet (ORB-155), or they filled the wizard and skipped the CV, which the
 *  wizard lets them do. */
function IncompletePill() {
  return <Badge variant="pill">Da completare</Badge>
}

/** Who the answers on a card come from, as the detail's «Scheda» row says it. */
function ownership(f: Freelancer): string {
  if (f.compilata_da === 'persona') return 'compilata dalla persona'
  return f.completa ? 'scritta dall’admin' : 'scritta dall’admin, da completare'
}

export function Header({ title, count, children }: { title: string; count?: number; children?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-5">
      <h1 className="text-2xl font-semibold tracking-tight">
        {title}
        {count !== undefined && (
          <span className="ml-2 text-base font-normal text-muted-foreground">{count}</span>
        )}
      </h1>
      {children}
    </header>
  )
}

function StateFilter({
  states,
  value,
  onChange,
}: {
  states: readonly string[]
  value: string | undefined
  onChange: (value: string | undefined) => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtra per stato">
      {[undefined, ...states].map((state) => (
        <Button
          key={state ?? 'tutti'}
          type="button"
          size="sm"
          variant={value === state ? 'default' : 'outline'}
          onClick={() => onChange(state)}
        >
          {state ? STATE_LABELS[state] : 'Tutti'}
        </Button>
      ))}
    </div>
  )
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-6 py-10 text-center text-sm text-muted-foreground">{children}</p>
}

/** One number on a stats page («La guida», «Accessi»), inside a `<dl>`. */
export function Figure({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-3xl font-semibold tracking-tight">
        {value}
        {note && <span className="ml-2 text-base font-normal text-muted-foreground">{note}</span>}
      </dd>
    </div>
  )
}

// ---- talenti -----------------------------------------------------------------------------

/** «Talenti»: every freelancer card and every bare sign-up as one list (REB-282/283),
 *  `stato` `lead` for the bare ones and the freelancer's own state otherwise -- the
 *  single list that replaced «Developer e CTO» and «Iscrizioni». A card row opens the
 *  existing freelancer detail; a lead row opens the page that offers to draft one. */
export function AdminTalenti() {
  const [stato, setStato] = useState<string | undefined>(undefined)
  const list = useQuery({ queryKey: ['talenti', stato], queryFn: () => admin.talenti(stato) })
  return (
    <>
      <Header title="Talenti" count={list.data?.totale}>
        <StateFilter states={FREELANCER_LIST_STATES} value={stato} onChange={setStato} />
      </Header>
      {list.isError ? (
        <Empty>Non riesco a leggere la lista.</Empty>
      ) : list.isPending ? (
        <Empty>Caricamento…</Empty>
      ) : list.data.items.length === 0 ? (
        <Empty>Nessun profilo qui.</Empty>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="px-6 py-2 font-medium">Chi</th>
              <th className="px-3 py-2 font-medium">Stato</th>
              <th className="px-3 py-2 font-medium">Provenienza</th>
              <th className="px-6 py-2 text-right font-medium">Quando</th>
            </tr>
          </thead>
          <tbody>
            {list.data.items.map((item) => (
              <TalentoRow key={item.id} item={item} />
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

function TalentoRow({ item }: { item: Talento }) {
  const name = [item.nome, item.cognome].filter(Boolean).join(' ')
  const to = item.stato === 'lead' ? '/admin/talenti/$id' : '/admin/freelance/$id'
  return (
    <tr className="border-b last:border-0 hover:bg-muted">
      <td className="px-6 py-2.5">
        <Link to={to} params={{ id: item.id }} className="font-medium hover:underline">
          {name || '—'}
        </Link>
        <p className="text-xs text-muted-foreground">{item.email}</p>
      </td>
      <td className="px-3 py-2.5">
        <StatePill stato={item.stato} />
      </td>
      <td className="px-3 py-2.5 text-muted-foreground">{item.origine}</td>
      <td className="px-6 py-2.5 text-right text-muted-foreground">{formatDate(item.created_at)}</td>
    </tr>
  )
}

interface LeadDraft {
  nome: string
  cognome: string
  linkedin_url: string
  posizione: string
  tariffa_giornaliera: string
  remoto: Remoto | ''
  links: string
  fonti: string
}

const LEAD_DRAFT_EMPTY: LeadDraft = {
  nome: '',
  cognome: '',
  linkedin_url: '',
  posizione: '',
  tariffa_giornaliera: '',
  remoto: '',
  links: '',
  fonti: '',
}

/** A bare sign-up (ORB-163, REB-283): what the landing knows, and the form that turns
 *  it into a card in place, through the same `draft_from_signup` the MCP tool
 *  `create_freelancer_from_signup` calls (ORB-155). One line per URL for «Link» and
 *  «Fonti»; at least one source is required, since a card written from research with
 *  no source is a card nobody can check. The row itself comes from the `talenti` list
 *  (`stato: 'lead'`): there is no single-sign-up fetch, so a direct visit refetches
 *  that page and reads its own row out of it. */
export function AdminTalentoLead() {
  const { id } = useParams({ from: '/signedIn/admin/talenti/$id' })
  const navigate = useNavigate()
  const client = useQueryClient()
  const leads = useQuery({ queryKey: ['talenti', 'lead'], queryFn: () => admin.talenti('lead') })
  const lead = leads.data?.items.find((item) => item.id === id)
  const [draft, setDraft] = useState(LEAD_DRAFT_EMPTY)
  const seeded = useRef(false)
  useEffect(() => {
    if (lead && !seeded.current) {
      seeded.current = true
      setDraft((current) => ({
        ...current,
        nome: lead.nome ?? current.nome,
        cognome: lead.cognome ?? current.cognome,
        linkedin_url: lead.linkedin_url ?? current.linkedin_url,
      }))
    }
  }, [lead])

  const draftCard = useMutation({
    mutationFn: (data: FreelancerDraft) => admin.draftFromSignup(id, data),
    onSuccess: (created) => {
      void client.invalidateQueries({ queryKey: ['talenti'] })
      void navigate({ to: '/admin/freelance/$id', params: { id: created.id } })
    },
  })
  const failure = draftCard.error instanceof ApiError ? draftCard.error : null
  const message = failure ? failure.message : draftCard.error ? 'Non riesco a creare la scheda.' : null
  const wrong = (field: string) => failure?.fields.includes(field) || undefined

  function field(name: keyof LeadDraft) {
    return (value: string) => setDraft((current) => ({ ...current, [name]: value }))
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    draftCard.mutate({
      nome: draft.nome.trim(),
      cognome: draft.cognome.trim(),
      linkedin_url: draft.linkedin_url.trim() || undefined,
      posizione: draft.posizione.trim() || undefined,
      tariffa_giornaliera: draft.tariffa_giornaliera.replace(',', '.').trim() || undefined,
      remoto: draft.remoto || undefined,
      links: draft.links.split('\n').map((line) => line.trim()).filter(Boolean),
      fonti: draft.fonti.split('\n').map((line) => line.trim()).filter(Boolean),
    })
  }

  if (leads.isError) return <Empty>Non riesco a leggere questo lead.</Empty>
  if (leads.isPending) return <Empty>Caricamento…</Empty>
  if (!lead) return <Empty>Lead non trovato.</Empty>
  return (
    <>
      <Header title={[lead.nome, lead.cognome].filter(Boolean).join(' ') || lead.email}>
        <StatePill stato="lead" />
      </Header>
      <div className="grid gap-6 p-6 lg:grid-cols-3">
        <dl className="space-y-3 text-sm lg:col-span-2">
          <Row label="Email">
            <a className="underline underline-offset-2" href={`mailto:${lead.email}`}>
              {lead.email}
            </a>
          </Row>
          <Row label="LinkedIn">
            {lead.linkedin_url ? (
              <a className="underline underline-offset-2" href={lead.linkedin_url} target="_blank" rel="noreferrer">
                {lead.linkedin_url}
              </a>
            ) : (
              '—'
            )}
          </Row>
          <Row label="Arrivato">
            {formatDate(lead.created_at)}
            {lead.utm_source ? ` · da ${lead.utm_source}` : ''}
          </Row>
        </dl>
        <form onSubmit={submit} className="space-y-3 rounded-2xl border bg-muted/40 p-4">
          <p className="text-sm font-medium">Scrivi la scheda</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-nome">Nome</Label>
              <Input
                id="lead-nome"
                required
                maxLength={120}
                value={draft.nome}
                onChange={(event) => field('nome')(event.target.value)}
                aria-invalid={wrong('nome')}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-cognome">Cognome</Label>
              <Input
                id="lead-cognome"
                required
                maxLength={120}
                value={draft.cognome}
                onChange={(event) => field('cognome')(event.target.value)}
                aria-invalid={wrong('cognome')}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lead-linkedin">LinkedIn</Label>
            <Input
              id="lead-linkedin"
              value={draft.linkedin_url}
              onChange={(event) => field('linkedin_url')(event.target.value)}
              aria-invalid={wrong('linkedin_url')}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lead-posizione">Posizione</Label>
            <Input
              id="lead-posizione"
              value={draft.posizione}
              onChange={(event) => field('posizione')(event.target.value)}
              aria-invalid={wrong('posizione')}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="lead-tariffa">Tariffa a giornata</Label>
              <Input
                id="lead-tariffa"
                inputMode="decimal"
                value={draft.tariffa_giornaliera}
                onChange={(event) => field('tariffa_giornaliera')(event.target.value)}
                aria-invalid={wrong('tariffa_giornaliera')}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-remoto">Modalità</Label>
              <select
                id="lead-remoto"
                value={draft.remoto}
                onChange={(event) => field('remoto')(event.target.value)}
                className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <option value="">—</option>
                {(Object.keys(REMOTO_LABELS) as Remoto[]).map((value) => (
                  <option key={value} value={value}>
                    {REMOTO_LABELS[value]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lead-links">Link</Label>
            <Textarea
              id="lead-links"
              rows={2}
              placeholder="Un URL per riga"
              value={draft.links}
              onChange={(event) => field('links')(event.target.value)}
              aria-invalid={wrong('links')}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lead-fonti">Fonti</Label>
            <Textarea
              id="lead-fonti"
              required
              rows={2}
              placeholder="Da dove viene questa scheda: un URL per riga"
              value={draft.fonti}
              onChange={(event) => field('fonti')(event.target.value)}
              aria-invalid={wrong('fonti')}
            />
          </div>
          <Button type="submit" size="sm" disabled={draftCard.isPending}>
            {draftCard.isPending ? 'Creo…' : 'Crea scheda'}
          </Button>
          {message && (
            <p role="alert" className="text-sm text-destructive">
              {message}
            </p>
          )}
        </form>
      </div>
      <p className="px-6 pb-6">
        <Link to="/admin/talenti" className="inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline">
          <ArrowLeft className="size-4" /> Tutti i talenti
        </Link>
      </p>
    </>
  )
}

function StatusEditor({
  states,
  stato,
  note,
  onSave,
  saving,
}: {
  states: readonly string[]
  stato: string
  note: string | null
  onSave: (stato: string, note: string) => void
  saving: boolean
}) {
  const [draftState, setDraftState] = useState(stato)
  const [draftNote, setDraftNote] = useState(note ?? '')
  return (
    <div className="space-y-3 rounded-2xl border bg-muted/40 p-4">
      <p className="text-sm font-medium">Stato e note</p>
      <StateFilter states={states} value={draftState} onChange={(value) => value && setDraftState(value)} />
      <Textarea
        aria-label="Note"
        value={draftNote}
        onChange={(event) => setDraftNote(event.target.value)}
        rows={3}
        placeholder="Una nota per chi rileggerà questa scheda"
      />
      <Button size="sm" onClick={() => onSave(draftState, draftNote)} disabled={saving}>
        {saving ? 'Salvo…' : 'Salva'}
      </Button>
    </div>
  )
}

/** What REB-284 adds to the freelancer detail beyond `Freelancer`: everywhere else in
 *  the hub that already knows this address, fetched server-side in the same call so
 *  the page does not fan out four requests of its own. */
interface FreelancerDetail extends Freelancer {
  /** The sign-up's own attribution, if this address left one on the landing --
   *  separate from `utm_source` above (the card's own), since the two can differ. */
  iscrizione_utm: {
    utm_source: string | null
    utm_medium: string | null
    utm_campaign: string | null
    utm_content: string | null
    utm_term: string | null
    utm_id: string | null
  } | null
  ultimi_accessi: { id: string; logged_at: string }[]
  ultimi_download_guida: { id: string; downloaded_at: string }[]
  pigro_slug: string | null
}

const ISCRIZIONE_UTM_LABELS: [key: keyof NonNullable<FreelancerDetail['iscrizione_utm']>, label: string][] = [
  ['utm_source', 'Sorgente'],
  ['utm_medium', 'Medium'],
  ['utm_campaign', 'Campagna'],
  ['utm_content', 'Contenuto'],
  ['utm_term', 'Termine'],
  ['utm_id', 'Id'],
]

/** The sign-up this address left on the landing, if it did, with its own UTM
 *  (REB-284): a section of its own since an admin-drafted card copies the signup's
 *  UTM onto the card at creation but a wizard card keeps its own, and the two can
 *  genuinely differ from what «Arrivato» shows above. */
function FreelancerIscrizione({ utm }: { utm: FreelancerDetail['iscrizione_utm'] }) {
  const known = utm ? ISCRIZIONE_UTM_LABELS.filter(([key]) => utm[key] !== null) : []
  return (
    <section className="space-y-3 px-6 pb-6">
      <h2 className="text-sm font-medium">Iscrizione alla newsletter</h2>
      {known.length ? (
        <dl className="space-y-2 text-sm">
          {known.map(([key, label]) => (
            <Row key={key} label={label}>{utm?.[key]}</Row>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">
          {utm ? 'Iscritta, senza UTM registrati.' : 'Nessuna iscrizione con questo indirizzo.'}
        </p>
      )}
    </section>
  )
}

/** A short list of dated events («Ultimi accessi», «Download della guida»), newest
 *  first, with an empty state instead of nothing when there are none (REB-284). */
function RecentEvents({
  title,
  empty,
  items,
}: {
  title: string
  empty: string
  items: { id: string; when: string }[]
}) {
  return (
    <section className="space-y-3 px-6 pb-6">
      <h2 className="text-sm font-medium">{title}</h2>
      {items.length ? (
        <ul className="space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.id}>{formatDateTime(item.when)}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </section>
  )
}

export function AdminFreelancerDetail() {
  const { id } = useParams({ from: '/signedIn/admin/freelance/$id' })
  const client = useQueryClient()
  const row = useQuery({
    queryKey: ['freelancer', id],
    queryFn: async () => (await admin.freelancer(id)) as FreelancerDetail,
  })
  const move = useMutation({
    mutationFn: ({ stato, note }: { stato: string; note: string }) =>
      admin.moveFreelancer(id, stato, note.trim() || null),
    // The PATCH answers the plain card, not the REB-284 sections: merged onto the
    // cached detail rather than replacing it, or a save would wipe them from view.
    onSuccess: (updated: Freelancer) => {
      client.setQueryData<FreelancerDetail>(['freelancer', id], (current) =>
        current && { ...current, ...updated },
      )
      void client.invalidateQueries({ queryKey: ['freelancers'] })
    },
  })
  // The thread lives on the detail row, so a new comment goes into the same cache entry
  // and nothing is fetched twice.
  const onCommentAdded = (created: Comment) =>
    client.setQueryData<FreelancerDetail>(['freelancer', id], (current) =>
      current && { ...current, commenti: [created, ...current.commenti] },
    )
  if (row.isError) return <Empty>Scheda non trovata.</Empty>
  if (row.isPending) return <Empty>Caricamento…</Empty>
  const f = row.data
  return (
    <>
      <Header title={`${f.nome} ${f.cognome}`}>
        <div className="flex flex-wrap items-center gap-2">
          <StatePill stato={f.stato} />
          {!f.completa && <IncompletePill />}
          {f.cv_filename !== null && f.cv_size !== null && (
            <Button asChild variant="outline" size="sm">
              <a href={admin.cvUrl(f.id)}>
                <Download className="mr-2 size-4" />
                CV · {formatBytes(f.cv_size)}
              </a>
            </Button>
          )}
        </div>
      </Header>
      <div className="grid gap-6 p-6 lg:grid-cols-3">
        <dl className="space-y-3 text-sm lg:col-span-2">
          <Row label="Email"><a className="underline underline-offset-2" href={`mailto:${f.email}`}>{f.email}</a></Row>
          <Row label="Posizione">{f.posizione ?? '—'}</Row>
          <Row label="Tariffa a giornata">
            {f.tariffa_giornaliera === null ? '—' : formatEuro(f.tariffa_giornaliera)}
          </Row>
          <Row label="Modalità">{f.remoto ? REMOTO_LABELS[f.remoto] : '—'}</Row>
          <Row label="LinkedIn">
            {f.linkedin_url ? <a className="underline underline-offset-2" href={f.linkedin_url} target="_blank" rel="noreferrer">{f.linkedin_url}</a> : '—'}
          </Row>
          <Row label="Link">
            {f.links.length ? (
              <ul className="space-y-1">
                {f.links.map((link) => (
                  <li key={link}><a className="underline underline-offset-2" href={link} target="_blank" rel="noreferrer">{link}</a></li>
                ))}
              </ul>
            ) : '—'}
          </Row>
          <Row label="Arrivato">{formatDate(f.created_at)}{f.utm_source ? ` · da ${f.utm_source}` : ''}{f.origine ? ` · pagina ${f.origine}` : ''}</Row>
          <Row label="Provenienza">{f.provenienza}</Row>
          <Row label="Accessi">
            {f.accessi === 0 || f.ultimo_accesso === null
              ? 'Mai entrato'
              : `${f.accessi} · ultimo ${formatDateTime(f.ultimo_accesso)}`}
          </Row>
          <Row label="Scheda">{ownership(f)}</Row>
        </dl>
        <StatusEditor
          states={FREELANCER_STATES}
          stato={f.stato}
          note={f.note}
          saving={move.isPending}
          onSave={(stato, note) => move.mutate({ stato, note })}
        />
      </div>
      <FreelancerIscrizione utm={f.iscrizione_utm} />
      <RecentEvents
        title="Ultimi accessi"
        empty="Non è mai entrata."
        items={f.ultimi_accessi.map((login) => ({ id: login.id, when: login.logged_at }))}
      />
      <RecentEvents
        title="Download della guida"
        empty="Non ha scaricato la guida."
        items={f.ultimi_download_guida.map((download) => ({
          id: download.id,
          when: download.downloaded_at,
        }))}
      />
      {f.pigro_slug && (
        <section className="space-y-2 px-6 pb-6">
          <h2 className="text-sm font-medium">Spazio PigroCRM</h2>
          <p className="text-sm"><code className="rounded bg-muted px-1.5 py-0.5">{f.pigro_slug}</code></p>
        </section>
      )}
      <Comments kind="freelancers" id={f.id} comments={f.commenti} onAdded={onCommentAdded} />
      <p className="px-6 pb-6">
        <Link to="/admin/talenti" className="inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline">
          <ArrowLeft className="size-4" /> Tutti i talenti
        </Link>
      </p>
    </>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-3 border-b pb-3 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

// ---- companies -------------------------------------------------------------------------

export function AdminCompanies() {
  const [stato, setStato] = useState<string | undefined>(undefined)
  const list = useQuery({ queryKey: ['companies', stato], queryFn: () => admin.companies(stato) })
  return (
    <>
      <Header title="Aziende" count={list.data?.totale}>
        <StateFilter states={COMPANY_STATES} value={stato} onChange={setStato} />
      </Header>
      {list.isError ? (
        <Empty>Non riesco a leggere la lista.</Empty>
      ) : list.isPending ? (
        <Empty>Caricamento…</Empty>
      ) : list.data.items.length === 0 ? (
        <Empty>Nessuna richiesta qui.</Empty>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="px-6 py-2 font-medium">Azienda</th>
              <th className="px-3 py-2 font-medium">Progetto</th>
              <th className="px-3 py-2 font-medium">Periodo</th>
              <th className="px-3 py-2 text-right font-medium">Budget</th>
              <th className="px-3 py-2 font-medium">Stato</th>
              <th className="px-6 py-2 text-right font-medium">Quando</th>
            </tr>
          </thead>
          <tbody>
            {list.data.items.map((item) => (
              <tr key={item.id} className="border-b last:border-0 hover:bg-muted">
                <td className="px-6 py-2.5">
                  <Link to="/admin/aziende/$id" params={{ id: item.id }} className="font-medium hover:underline">
                    {item.nome_azienda}
                  </Link>
                  <p className="text-xs text-muted-foreground">{item.referente} · {item.email}</p>
                </td>
                <td className="max-w-xs truncate px-3 py-2.5">{item.progetto}</td>
                <td className="px-3 py-2.5">dal {formatDate(item.periodo_da)}, {item.durata}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatEuro(item.budget_giornaliero)}</td>
                <td className="px-3 py-2.5"><StatePill stato={item.stato} /></td>
                <td className="px-6 py-2.5 text-right text-muted-foreground">{formatDate(item.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

export function AdminCompanyDetail() {
  const { id } = useParams({ from: '/signedIn/admin/aziende/$id' })
  const client = useQueryClient()
  const row = useQuery({ queryKey: ['company', id], queryFn: () => admin.company(id) })
  const move = useMutation({
    mutationFn: ({ stato, note }: { stato: string; note: string }) =>
      admin.moveCompany(id, stato, note.trim() || null),
    onSuccess: (updated: Company) => {
      client.setQueryData(['company', id], updated)
      void client.invalidateQueries({ queryKey: ['companies'] })
    },
  })
  const onCommentAdded = (created: Comment) =>
    client.setQueryData<Company>(['company', id], (current) =>
      current && { ...current, commenti: [created, ...current.commenti] },
    )
  if (row.isError) return <Empty>Richiesta non trovata.</Empty>
  if (row.isPending) return <Empty>Caricamento…</Empty>
  const c = row.data
  return (
    <>
      <Header title={c.nome_azienda}><StatePill stato={c.stato} /></Header>
      <div className="grid gap-6 p-6 lg:grid-cols-3">
        <dl className="space-y-3 text-sm lg:col-span-2">
          <Row label="Referente">{c.referente} · <a className="underline underline-offset-2" href={`mailto:${c.email}`}>{c.email}</a></Row>
          <Row label="Progetto"><p className="whitespace-pre-wrap">{c.progetto}</p></Row>
          <Row label="Periodo">dal {formatDate(c.periodo_da)}, {c.durata}</Row>
          <Row label="Budget a giornata">{formatEuro(c.budget_giornaliero)}</Row>
          <Row label="Arrivata">{formatDate(c.created_at)}{c.utm_source ? ` · da ${c.utm_source}` : ''}{c.origine ? ` · pagina ${c.origine}` : ''}</Row>
        </dl>
        <StatusEditor
          states={COMPANY_STATES}
          stato={c.stato}
          note={c.note}
          saving={move.isPending}
          onSave={(stato, note) => move.mutate({ stato, note })}
        />
      </div>
      <Comments kind="companies" id={c.id} comments={c.commenti} onAdded={onCommentAdded} />
      <p className="px-6 pb-6">
        <Link to="/admin/aziende" className="inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline">
          <ArrowLeft className="size-4" /> Tutte le aziende
        </Link>
      </p>
    </>
  )
}
