import { Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ApiError, type FreelancerApplication } from '@/lib/api'
import { toApplication, toUpdate, useMember, useReplaceCv, useUpdateProfile } from '@/lib/member'
import { FREELANCER_STEPS } from '@/pages/FreelancerWizard'
import type { Step } from '@/wizard/Wizard'

/**
 * The wizard's steps, as a form: every question at once, because the person is
 * correcting and not answering for the first time. The email is not among them (it is
 * the identity the link proved). Everything else, control and rule alike, is the
 * wizard's own.
 *
 * The CV is optional here in both cases, and the hint is what differs. While we hold
 * one, `null` keeps it. When we hold none -- a card an admin wrote from a signup
 * (ORB-155), or a person who skipped the step in the wizard -- this used to be the one
 * required question on the page, which since the wizard stopped demanding a PDF would
 * only have moved the same wall one step later: somebody correcting their rate would
 * have been told to produce a CV first, and would have left with neither saved.
 */
export function editSteps(hasCv: boolean): Step<FreelancerApplication>[] {
  return FREELANCER_STEPS.filter((step) => step.id !== 'email').map((step) =>
    step.id === 'cv'
      ? {
          ...step,
          optional: true,
          hint: hasCv
            ? 'Solo se vuoi sostituirlo: un PDF, al massimo 5 MB. Altrimenti teniamo quello che abbiamo.'
            : 'Non ne abbiamo ancora uno. Un PDF, al massimo 5 MB: caricalo adesso o quando vuoi.',
        }
      : step,
  )
}

export function Modifica() {
  const me = useMember()
  const navigate = useNavigate()
  const update = useUpdateProfile()
  const replaceCv = useReplaceCv()
  const [draft, setDraft] = useState<FreelancerApplication | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [failure, setFailure] = useState<string | null>(null)

  // State that follows a prop, adjusted during render: the draft starts from the
  // profile the first time it is known, and never again while the person is typing.
  if (draft === null && me.data) setDraft(toApplication(me.data))
  if (!me.data || draft === null) {
    return <p className="text-sm text-muted-foreground">Caricamento…</p>
  }
  const value = draft
  const steps = editSteps(me.data.cv_filename !== null)
  const set = (patch: Partial<FreelancerApplication>) =>
    setDraft((current) => (current ? { ...current, ...patch } : current))
  const saving = update.isPending || replaceCv.isPending

  async function save() {
    setFailure(null)
    const problems: Record<string, string> = {}
    for (const step of steps) {
      const problem = step.validate(value)
      if (problem) problems[step.id] = problem
    }
    setErrors(problems)
    if (Object.keys(problems).length) return
    let saved = false
    try {
      await update.mutateAsync(toUpdate(value))
      saved = true
      if (value.cv) await replaceCv.mutateAsync(value.cv)
      void navigate({ to: '/io' })
    } catch (error) {
      const refusal = error instanceof ApiError ? error : null
      // The PATCH and the CV replacement are two requests: when the first has already
      // gone through, a refusal on the second must not read as if nothing was saved.
      const suffix = saved ? ' Le altre risposte sono salvate.' : ''
      const known = refusal?.fields.filter((field) => steps.some((step) => step.id === field)) ?? []
      if (known.length) {
        setErrors(Object.fromEntries(known.map((field) => [field, refusal!.message + suffix])))
      } else {
        setFailure((refusal?.message ?? 'Non siamo riusciti a salvare. Riprova.') + suffix)
      }
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">La tua area</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Correggi quello che ci hai mandato</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ti scriviamo a <span className="font-medium text-foreground">{me.data.email}</span>: per
          cambiare indirizzo, rifai la candidatura con quello nuovo.
        </p>
      </div>

      {steps.map((step) => (
        <section key={step.id} className="space-y-3" aria-labelledby={`edit-${step.id}`}>
          <div>
            <h2 id={`edit-${step.id}`} className="text-lg font-semibold tracking-tight">
              {step.title}
              {step.optional && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">(facoltativo)</span>
              )}
            </h2>
            {step.hint && <p className="mt-1 text-sm text-muted-foreground">{step.hint}</p>}
          </div>
          {step.render({
            value,
            set,
            next: () => void save(),
            error: errors[step.id] ?? null,
            autoFocus: false,
          })}
          {errors[step.id] && (
            <p role="alert" className="text-sm text-destructive">
              {errors[step.id]}
            </p>
          )}
        </section>
      ))}

      {failure && (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <div className="flex items-center justify-between">
        <Button asChild variant="ghost">
          <Link to="/io">Annulla</Link>
        </Button>
        <Button type="button" onClick={() => void save()} disabled={saving}>
          {saving ? 'Salvo…' : 'Salva'}
        </Button>
      </div>
    </div>
  )
}
