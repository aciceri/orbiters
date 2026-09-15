import { useLocation, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { distinctId } from '@rebase/analytics/browser'
import { useWizardAnalytics } from '@/lib/analytics'
import { ApiError, requestPeople, type CompanyRequest } from '@/lib/api'
import { resolveAttribution } from '@/lib/utm'
import { clearDraft, loadDraft, saveDraft } from '@/wizard/draft'
import { LongTextField, TextField } from '@/wizard/fields'
import { Wizard, type Step } from '@/wizard/Wizard'

const EMPTY: CompanyRequest = {
  nome_azienda: '',
  referente: '',
  email: '',
  progetto: '',
  periodo_da: '',
  durata: '',
  budget_giornaliero: '',
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export const COMPANY_STEPS: Step<CompanyRequest>[] = [
  {
    id: 'nome_azienda',
    title: 'Come si chiama la tua azienda?',
    render: ({ value, set, autoFocus }) => (
      <TextField
        aria-label="Azienda"
        placeholder="ACME Srl"
        value={value.nome_azienda}
        onChange={(nome_azienda) => set({ nome_azienda })}
        autoFocus={autoFocus}
      />
    ),
    validate: (value) => (value.nome_azienda.trim() ? null : 'Serve il nome dell’azienda.'),
    summary: (value) => value.nome_azienda.trim(),
  },
  {
    id: 'referente',
    title: 'Chi sei, e dove ti scriviamo?',
    render: ({ value, set, autoFocus }) => (
      <div className="grid gap-3">
        <TextField
          aria-label="Referente"
          placeholder="Nome e cognome"
          value={value.referente}
          onChange={(referente) => set({ referente })}
          autoFocus={autoFocus}
        />
        <TextField
          aria-label="Email"
          type="email"
          inputMode="email"
          placeholder="nome@azienda.it"
          value={value.email}
          onChange={(email) => set({ email })}
        />
      </div>
    ),
    validate: (value) =>
      value.referente.trim() && EMAIL.test(value.email.trim())
        ? null
        : 'Servono un referente e un indirizzo email valido.',
    summary: (value) => `${value.referente.trim()} · ${value.email.trim()}`,
  },
  {
    id: 'progetto',
    title: 'Raccontaci il progetto in due righe',
    hint: 'Cosa serve fare, con che stack o competenze, e cosa deve uscirne. Shift+Invio per andare a capo.',
    render: ({ value, set, autoFocus }) => (
      <LongTextField
        aria-label="Progetto"
        placeholder="Dobbiamo rifare il backend del portale clienti…"
        value={value.progetto}
        onChange={(progetto) => set({ progetto })}
        autoFocus={autoFocus}
      />
    ),
    validate: (value) =>
      value.progetto.trim().length >= 20 ? null : 'Due righe bastano, ma servono: almeno venti caratteri.',
    summary: (value) => value.progetto.trim(),
  },
  {
    id: 'periodo_da',
    title: 'Da quando, e per quanto?',
    hint: 'Anche approssimativo: «da ottobre, per tre mesi».',
    render: ({ value, set, autoFocus }) => (
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          aria-label="Da quando"
          type="date"
          value={value.periodo_da}
          onChange={(periodo_da) => set({ periodo_da })}
          autoFocus={autoFocus}
        />
        <TextField
          aria-label="Per quanto"
          placeholder="3 mesi"
          value={value.durata}
          onChange={(durata) => set({ durata })}
        />
      </div>
    ),
    validate: (value) =>
      /^\d{4}-\d{2}-\d{2}$/.test(value.periodo_da) && value.durata.trim()
        ? null
        : 'Servono una data di inizio e una durata.',
    summary: (value) => (value.periodo_da ? `dal ${value.periodo_da}, ${value.durata.trim()}` : ''),
  },
  {
    id: 'budget_giornaliero',
    title: 'Che budget hai per una giornata?',
    hint: 'In euro, IVA esclusa. Serve a proporti le persone giuste, non a trattare.',
    render: ({ value, set, autoFocus }) => (
      <div className="flex items-center gap-3">
        <TextField
          aria-label="Budget a giornata"
          inputMode="decimal"
          placeholder="500"
          value={value.budget_giornaliero}
          onChange={(budget_giornaliero) => set({ budget_giornaliero })}
          autoFocus={autoFocus}
        />
        <span className="text-lg text-muted-foreground">€ / giorno</span>
      </div>
    ),
    validate: (value) => {
      const number = Number(value.budget_giornaliero.replace(',', '.'))
      return Number.isFinite(number) && number >= 1 && number <= 99999 ? null : 'Serve una cifra, in euro.'
    },
    summary: (value) => (value.budget_giornaliero ? `${value.budget_giornaliero} € / giorno` : ''),
  },
]

export const COMPANY_DRAFT_KEY = 'rebase.wizard.azienda'

/** Above the first question, as on the freelance side (REB-215): what this is and how
 *  long it takes, before a company is asked its name. */
function Intro() {
  return (
    <aside
      aria-label="Cos’è rebase"
      className="border-l-4 border-(--landing-ink) bg-card py-2 pl-4 pr-2"
    >
      <p className="font-medium">rebase è la community di chi fa software in proprio in Italia.</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {COMPANY_STEPS.length} domande, un paio di minuti: chi siete, cosa cercate e con che
        budget, così vi proponiamo le persone giuste.
      </p>
    </aside>
  )
}

function ResumedNote({ onRestart }: { onRestart: () => void }) {
  return (
    <aside
      role="note"
      aria-label="Risposte ritrovate"
      className="mx-auto mb-8 flex w-full max-w-2xl flex-wrap items-center justify-between gap-2 border-(length:--landing-border-width) bg-card px-4 py-3 text-sm"
    >
      <span>Abbiamo ritrovato le risposte di prima: riprendi da dove eri.</span>
      <button type="button" className="font-medium underline underline-offset-2" onClick={onRestart}>
        Ricomincia
      </button>
    </aside>
  )
}

export function CompanyWizard() {
  const navigate = useNavigate()
  // The URL's own query string, from the router rather than `window`: the attribution
  // is whatever this page was opened with.
  const searchStr = useLocation({ select: (location) => location.searchStr })
  const analytics = useWizardAnalytics('azienda', searchStr)
  const [draft] = useState(() => loadDraft<CompanyRequest>(COMPANY_DRAFT_KEY))
  const [value, setValue] = useState<CompanyRequest>(() => ({ ...EMPTY, ...draft?.value }))
  const [index, setIndex] = useState(draft?.index ?? 0)
  const [resumed, setResumed] = useState(draft !== null)
  const [attempt, setAttempt] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<{ message: string; step?: string } | null>(null)

  // Once the application is in, nothing is saved again, whatever React still has to
  // flush: the next visit must open a blank form, not the one just sent.
  const sent = useRef(false)
  useEffect(() => {
    if (!sent.current) saveDraft(COMPANY_DRAFT_KEY, value, index)
  }, [value, index])

  function restart() {
    clearDraft(COMPANY_DRAFT_KEY)
    setValue(EMPTY)
    setIndex(0)
    setResumed(false)
    setAttempt((current) => current + 1)
  }

  async function submit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await requestPeople(
        { ...value, budget_giornaliero: value.budget_giornaliero.replace(',', '.') },
        resolveAttribution(searchStr),
        distinctId(),
      )
      sent.current = true
      clearDraft(COMPANY_DRAFT_KEY)
      analytics.completed()
      void navigate({ to: '/grazie', search: { chi: 'azienda' } })
    } catch (error) {
      const failure = error instanceof ApiError ? error : null
      // `durata` shares the step with `periodo_da`; anything else names its own step.
      const field = failure?.fields[0]
      setSubmitError({
        message: failure?.message ?? 'Non siamo riusciti a inviare la richiesta. Riprova.',
        step: field === 'durata' ? 'periodo_da' : field,
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      {resumed && <ResumedNote onRestart={restart} />}
      <Wizard
        key={attempt}
        title="Cerchi persone"
        steps={COMPANY_STEPS}
        value={value}
        set={(patch) => setValue((current) => ({ ...current, ...patch }))}
        onSubmit={() => void submit()}
        submitting={submitting}
        submitError={submitError}
        submitLabel="Invia la richiesta"
        onStep={analytics.onStep}
        initialIndex={resumed ? (draft?.index ?? 0) : 0}
        onIndexChange={setIndex}
        intro={<Intro />}
      />
    </>
  )
}
