import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldOff, UserPlus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Badge } from '@rebase/ui/badge'
import { Button } from '@rebase/ui/button'
import { Input } from '@rebase/ui/input'
import { Label } from '@rebase/ui/label'
import { ApiError, admin, type Admin } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { Empty, Header } from './lists'

const ADMINS_KEY = ['admins'] as const

interface Draft {
  email: string
  nome: string
  cognome: string
}

const EMPTY: Draft = { email: '', nome: '', cognome: '' }

/**
 * Who reads this area, and the one form that grants or revokes the role (ORB-123,
 * REB-279): typing an email promotes whatever `users` row already answers to it, or
 * creates a bare one from `nome`/`cognome` when none exists yet -- those two fields
 * only matter for a brand-new address, and the server ignores them harmlessly for one
 * it already knows. There is no password anywhere on this page any more: the magic
 * link is the only way in, for a member and an admin alike. Demoting is one click on
 * a row and is fully reversible, since nothing is deleted -- unlike the old
 * create/update dialog this replaces, which had no deactivation at all.
 */
export function AdminAdmins() {
  const client = useQueryClient()
  const list = useQuery({ queryKey: ADMINS_KEY, queryFn: () => admin.admins() })
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [done, setDone] = useState<{ verb: 'promosso' | 'rimosso'; email: string } | null>(null)

  const promote = useMutation({
    mutationFn: (data: Draft) =>
      admin.promote({
        email: data.email.trim(),
        nome: data.nome.trim() || undefined,
        cognome: data.cognome.trim() || undefined,
      }),
    onSuccess: (saved) => {
      setDraft(EMPTY)
      setDone({ verb: 'promosso', email: saved.email })
      void client.invalidateQueries({ queryKey: ADMINS_KEY })
    },
  })
  const demote = useMutation({
    mutationFn: (id: string) => admin.demote(id),
    onSuccess: (saved) => {
      setDone({ verb: 'rimosso', email: saved.email })
      void client.invalidateQueries({ queryKey: ADMINS_KEY })
    },
  })

  const failure = promote.error instanceof ApiError ? promote.error : null
  const message = failure
    ? failure.message
    : promote.error
      ? 'Non riesco a promuovere questo indirizzo.'
      : null
  const wrong = (field: keyof Draft) => failure?.fields.includes(field) || undefined

  function submit(event: FormEvent) {
    event.preventDefault()
    promote.mutate(draft)
  }

  function field(name: keyof Draft) {
    return (value: string) => setDraft((current) => ({ ...current, [name]: value }))
  }

  return (
    <>
      <Header title="Amministratori" count={list.data?.length} />

      <form
        onSubmit={submit}
        className="grid gap-4 border-b px-6 py-6 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"
      >
        <div className="space-y-2">
          <Label htmlFor="admin-email">Email</Label>
          <Input
            id="admin-email"
            type="email"
            required
            autoComplete="off"
            value={draft.email}
            onChange={(event) => field('email')(event.target.value)}
            aria-invalid={wrong('email')}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="admin-nome">Nome</Label>
          <Input
            id="admin-nome"
            maxLength={120}
            autoComplete="off"
            placeholder="Solo per un indirizzo nuovo"
            value={draft.nome}
            onChange={(event) => field('nome')(event.target.value)}
            aria-invalid={wrong('nome')}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="admin-cognome">Cognome</Label>
          <Input
            id="admin-cognome"
            maxLength={120}
            autoComplete="off"
            placeholder="Solo per un indirizzo nuovo"
            value={draft.cognome}
            onChange={(event) => field('cognome')(event.target.value)}
            aria-invalid={wrong('cognome')}
          />
        </div>
        <Button type="submit" disabled={promote.isPending}>
          <UserPlus data-icon="inline-start" />
          {promote.isPending ? 'Promuovo…' : 'Promuovi'}
        </Button>
        {message && (
          <p role="alert" className="text-sm text-destructive sm:col-span-4">
            {message}
          </p>
        )}
      </form>

      {/* Always mounted: a live region that appears already filled is often not read out. */}
      <p role="status" aria-live="polite" className={done ? 'border-b px-6 py-3 text-sm' : undefined}>
        {done?.verb === 'promosso' && (
          <>
            Amministratore promosso: <span className="font-medium">{done.email}</span>.
          </>
        )}
        {done?.verb === 'rimosso' && (
          <>
            Non è più amministratore: <span className="font-medium">{done.email}</span>.
          </>
        )}
      </p>

      {list.isError ? (
        <Empty>Non riesco a leggere la lista.</Empty>
      ) : list.isPending ? (
        <Empty>Caricamento…</Empty>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="px-6 py-2 font-medium">Chi</th>
              <th className="px-3 py-2 font-medium">Stato</th>
              <th className="px-3 py-2 text-right font-medium">Da quando</th>
              <th className="px-6 py-2">
                <span className="sr-only">Azioni</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {list.data.map((row: Admin) => (
              <tr key={row.id} className="border-b last:border-0 hover:bg-muted">
                <td className="px-6 py-2.5">
                  <p className="font-medium">{row.nome}</p>
                  <p className="text-xs text-muted-foreground">{row.email}</p>
                </td>
                <td className="px-3 py-2.5">
                  <Badge variant="pill">{row.attivo ? 'Attivo' : 'Disattivato'}</Badge>
                </td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{formatDate(row.created_at)}</td>
                <td className="px-6 py-1.5 text-right">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={demote.isPending}
                    onClick={() => demote.mutate(row.id)}
                  >
                    <ShieldOff className="mr-2 size-4" />
                    Rimuovi
                    <span className="sr-only">
                      {' '}
                      {row.nome} ({row.email}) da amministratore
                    </span>
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
