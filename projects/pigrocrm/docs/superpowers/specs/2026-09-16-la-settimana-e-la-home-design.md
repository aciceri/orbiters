# La settimana via mail, e una Home che porta dentro il lavoro

Design record del 2026-09-16, deciso con Ivan la sera del 15 e la mattina del 16. Quattro
card, un documento: REB-221 (il resoconto settimanale), REB-222 (la Home di uno spazio
vuoto), REB-223 (i clienti proposti da Gmail), REB-224 (la fattura consegnata
all'assistente). L'ordine di consegna è quello.

## 1. I dati che l'hanno deciso

Il 16 settembre il registro conta quattordici spazi. Sette persone sono entrate una volta
sola; nelle 48 ore precedenti PostHog non registra nessun login né alcuna azione su
`pigro.letsrebase.com`, solo pagine di login e Home. Nessuno spazio ha un cliente, un deal
o una fattura. Il programma di onboarding del 12 settembre (spazio nato pronto, login via
mail, «Get started» con l'assistente e i quattro primi passi, prompt pronti) è in
produzione dal 14 e non ha spostato nulla.

La lettura: il problema non è dentro lo schermo. Chi entra lo fa perché ha compilato il
wizard di rebase e PigroCRM è il perk; nessuno torna finché non ha una cosa vera da fare,
e la prima schermata gli chiede di scrivere a mano il proprio mondo prima di avergli
mostrato qualcosa di suo.

## 2. Le regole

- **Nulla si nasconde.** Il menu resta com'è: chi vuole fare a mano trova Clienti, Deal,
  Fatture e Ore dove sono sempre stati. Cambia solo la Home di uno spazio senza dati.
- **Le due porte e l'assistente coesistono.** Le porte creano i dati, l'assistente li usa;
  non è un bivio.
- **Solo assistente per la fattura.** Nessuna estrazione lato server, nessuna chiamata a
  un modello dall'API: il PDF lo legge l'agente con `read_document_text` e lo registra con
  `import_issued_invoice`. Deciso il 16.
- **La mail è il resoconto della settimana**, non un avviso: arriva a chiunque abbia
  almeno un dato nello spazio; silenzio per gli spazi vuoti.
- **Numeri con data e fonte**, come in ogni superficie: ogni riga della mail porta al
  filtro che la produce.

## 3. Il resoconto settimanale (REB-221)

### 3.1 Cosa arriva

Il lunedì alle 8 (Europe/Rome), oggetto composto dai fatti diversi da zero, nell'ordine:
«La tua settimana: 2 fatture emesse, 1.800 € da incassare», o «La tua settimana: 12 ore
registrate, 1 offerta in attesa», o «La tua settimana in PigroCRM» quando la settimana è
ferma. La settimana è quella appena chiusa, da lunedì a domenica.

Le sezioni, ognuna presente solo se ha righe, ognuna con il link alla lista già filtrata
(`?da=digest` su ogni link, così PostHog riconosce i rientri):

1. **Da incassare.** Le fatture scadute e non pagate, con cliente, importo e giorni di
   ritardo, dalla più in ritardo; poi quelle in scadenza nei prossimi sette giorni. Per
   ogni scaduta il link «Prepara il sollecito» porta alla fattura, da cui la bozza si
   genera come oggi (`SollecitiService.candidates` è la fonte).
2. **Da emettere.** I deal vinti senza fattura e le ore fatturabili non fatturate con il
   valore maturato (`AnalyticsService.unbilled_backlog`,
   `TimeEntryRepository.count_won_deals_to_invoice`).
3. **Emesse questa settimana.** Numero, cliente, importo, stato (emessa, trasmessa,
   incassata), e sotto il totale del mese in corso accanto a quello del mese scorso.
4. **Incassate questa settimana.** Chi ha pagato e quanto (`data_incasso` nella settimana).
5. **Le ore.** Totale della settimana per deal e i giorni senza ore
   (`TimeEntryRepository.week_hours` sulla settimana chiusa); la sezione esiste solo se
   nella settimana ci sono ore.
6. **In pipeline.** Deal aperti per fase con il valore (`DealRepository.pipeline_summary`),
   i deal mossi nella settimana (attività `stage_changed` sull'entità `deal`), le offerte
   in attesa di risposta (`DocumentRepository.pending_offers`).
7. **Da sistemare.** I tre segnali dell'operativa (fatturato ma non vinto, vinto ma da
   fatturare, scaduto e non incassato) con il conteggio e il link, quando almeno uno è
   maggiore di zero.

Chiusura variabile: se nella settimana non è successo nulla, «Settimana ferma: se hai un
preventivo da fare, l'assistente lo prepara in un minuto», con il prompt in chiaro.
In fondo, il link «Non inviarmi più il resoconto» verso le impostazioni del profilo.

### 3.2 Come si calcola

Un modulo nuovo, `pigrocrm/core/digest/`, con `DigestService(session, settings)` e
`build(actor, settimana: tuple[date, date]) -> WeeklyDigest`. `WeeklyDigest` è uno schema
Pydantic puro, senza HTML, con una lista per sezione e i totali già calcolati; la mail lo
rende, i test lo leggono. Il servizio compone chiamate esistenti e non ripete
aritmetica che altrove è già scritta: `DashboardService.get_operational_dashboard` per i
segnali (chiamata per prima, perché apre uno snapshot e pretende una sessione senza
transazione aperta), `SollecitiService.candidates`, `InvoiceService.list` con
`InvoiceListQuery` per scadenze, emesse e incassate, `AnalyticsService.unbilled_backlog`,
`DealRepository.pipeline_summary`, `ActivityRepository.by_kind(["stage_changed"])`
filtrato sulla settimana, `DocumentRepository.pending_offers`. Le sole somme nuove
(emesso e incassato per periodo, totale mese corrente e precedente) entrano in
`InvoiceRepository` accanto a `sum_da_incassare`.

La settimana viene da `current_week(settings)` spostata indietro di sette giorni: mai
`date.today()`. Il comando accetta `--data YYYY-MM-DD` per calcolare la settimana che
contiene quel giorno (test, reinvii) e `--slug` per un solo spazio, `--dry-run` per
stampare senza inviare.

### 3.3 A chi, e una volta sola

Destinatari: gli utenti attivi dello spazio con `digest_settimanale` acceso; il campo è
una colonna nuova su `users`, default vero, migrazione `0035`. L'attore delle letture è
il proprietario dello spazio (`Tenant.owner_email` risolto con
`UserRepository.get_by_email`), costruito come `_cron_actor` in `cli.py`
(`Actor(type="system", role=user.ruolo)`); uno spazio il cui proprietario è disattivato
viene saltato con una riga di log, non fallisce il ciclo.

Idempotenza: una tabella `digests` nel database dello spazio (stessa migrazione
`0035`): `id`, `settimana` (`YYYY-Www`, unica), `inviato_a` (JSONB, gli indirizzi),
`occurred_at`. Il comando salta la settimana già registrata; `--forza` la rimanda e
aggiorna la riga. Una riga di attività `digest.inviato` sull'entità `digest` con i
conteggi (quante sezioni, quanti destinatari), mai gli importi; e un evento PostHog
lato server `digest_inviato` per destinatario, `distinct_id` l'id dell'utente (è lo
stesso con cui il browser lo identifica), inviato solo se `PIGROCRM_POSTHOG_KEY` è
impostata: `posthog` entra nelle dipendenze dichiarate di core, che
`test_architecture.py` legge alla lettera.

Spazi saltati: quelli senza nessun cliente, deal, fattura o voce di tempo (una lettura di
una riga ciascuna, come i primi passi). Il comando stampa una riga per spazio:
`slug: inviato a N` / `slug: vuoto` / `slug: già inviato per 2026-W38` / `slug: errore <motivo>`,
e non fallisce mai il ciclo per un solo spazio, come `ensure-space-defaults`.

### 3.4 Il comando e il cron

`pigrocrm digest` in `cli.py`, accanto a `gmail-sync`, che copia il ciclo di
`ensure_space_defaults` sul registro (`tenant_database_url`, un engine per spazio,
`dispose()` sempre) e prende l'`EmailSender` da `sender_from_settings(get_settings())`
(la chiave Resend è di piattaforma). L'URL pubblico dei link viene da
`space_base_settings(settings, slug).public_url`. Sul server, nel crontab che già porta
il sync Gmail:

```
0 8 * * 1 cd /opt/pigrocrm/projects/pigrocrm && docker compose --env-file ../../.env exec -T api uv run --no-sync pigrocrm digest >> /var/log/pigrocrm-digest.log 2>&1
```

con l'ora corretta per il fuso del server se non è Europe/Rome. La riga entra nel runbook
del cron Gmail, che diventa il runbook dei cron.

### 3.5 La mail

`digest_mail(to, digest: WeeklyDigest, *, public_url) -> Mail` in `core/mail.py`, con lo
stesso telaio (`_frame`, `_button`, `_quiet_link`), ogni valore esterno passato da
`html.escape`, e un `text` che dice le stesse cose in righe. Importi in euro con la
virgola, date in italiano breve («lun 8 set»). Niente nomi di persone oltre al cliente
della riga, che è già dello spazio.

### 3.6 Il profilo

`digest_settimanale` esposto dove l'utente modifica il proprio profilo (schema di
aggiornamento utente e pannello impostazioni), come interruttore «Ricevi il resoconto
settimanale». Il link nella mail porta lì.

### 3.7 Verifica

Test core su `db_session`: `build` con fatture scadute, emesse e incassate nella
settimana, ore, un deal mosso, un'offerta inviata, e uno spazio vuoto che non produce
nulla; la mail con `RecordingSender` (sezioni presenti e assenti, oggetto composto,
link con `?da=digest`, nessun importo nell'attività); il comando in `test_cli_*` con il
registro nel container: due esecuzioni, una sola mail, `--forza` che rimanda,
`--dry-run` che non scrive. Poi dal vivo: primo invio sullo spazio humancraft di Ivan,
mail letta, evento `digest_inviato` in PostHog.

## 4. La Home di uno spazio vuoto (REB-222)

### 4.1 Quando

Uno spazio è vuoto quando le sei letture di `useFirstSteps` dicono che non esiste alcun
cliente, deal, voce di tempo e documento. Finché è così, la Home (`/app`) mostra la pagina
in tre blocchi al posto della dashboard; `/app/get-started` resta nel menu e mostra la
stessa pagina, così chi ci arriva dal menu vede la stessa cosa. Il redirect «una volta
sola» di §6.7 del 12 settembre non serve più e viene tolto: la Home è già quella pagina.
Quando lo spazio ha dati, la Home torna la dashboard operativa con una card «Completa lo
spazio» finché un passo resta aperto, poi niente.

### 4.2 I tre blocchi

**Porta dentro il tuo lavoro.** Due porte affiancate. «Collega Gmail»: lo stato viene da
`useGmailHealth`; se la casella non è collegata, il bottone è l'anchor a
`${tenantPrefix}/api/gmail/oauth/start` come nel pannello Gmail, e il callback OAuth torna
alla Home (`esito=collegato`) invece che alle impostazioni quando lo spazio è vuoto; se è
collegata, la porta mostra la lista dei clienti proposti (REB-223) o, finché quella card
non è in produzione, la riga «Casella collegata: i tuoi clienti arrivano tra poco».
«Carica l'ultima fattura che hai emesso»: la dropzone dei documenti, solo PDF, e la
consegna all'assistente (REB-224).

**Fai lavorare l'assistente.** Il corpo di `ConnectAgentDialog` estratto in un
`ConnectAgentPanel` che il dialogo e la Home condividono: endpoint MCP, creazione del
token, i tre modi di collegarlo (Claude Code con il comando, Claude Desktop con il JSON,
ChatGPT con l'indirizzo del connettore), e sotto i prompt pronti di REB-182 con
`CopyPrompt`. Quando un token personale esiste già, il blocco si riduce ai prompt.

**Oppure a mano.** I quattro primi passi di `firstSteps.ts`, ciascuno con due link
affiancati: la schermata (`step.to`) e il prompt (`STEP_PROMPTS[id]`). Le regole di §6.7
restano: spuntato quando la cosa esiste, testo per chi non può scrivere, nessun «Nascondi».

### 4.3 Verifica

Test di pagina come `GetStartedPage.test.tsx` (API finta per percorso, `QueryClient`
nuovo): spazio vuoto → tre blocchi; casella collegata → porta nello stato collegato;
token esistente → blocco assistente ridotto; spazio con un cliente → dashboard e card
«Completa lo spazio»; tutto fatto → dashboard sola. Coppia prima/dopo nella PR, e la Home
letta sull'anteprima con uno spazio di prova.

## 5. I clienti proposti da Gmail (REB-223)

**Una decisione prima del codice.** Uno spazio non eredita il client Google della
piattaforma: `space_base_settings` azzera `google_client_id`, `google_client_secret` e
`google_token_key` per ogni slug, e il callback OAuth è `{public_url}/{slug}/api/gmail/
oauth/callback`, un indirizzo per spazio che Google pretende registrato uno per uno. Oggi
quindi «Collega Gmail» per uno spazio vuol dire «crea un client OAuth nella console Google
Cloud», che nessun freelance farà. Perché la porta esista serve: un client condiviso (la
piattaforma presta il suo, con un'impostazione `PIGROCRM_GOOGLE_SHARED_CLIENT` che
`space_base_settings` rispetta), un solo callback alla radice che smista sullo slug
portato nello `state`, e la verifica Google dell'app oltre i cento account di prova. È
una card a sé, da decidere con Ivan prima di REB-223; fino ad allora la porta mostra
«Collega Gmail» solo negli spazi che hanno già un client (`gmail_configurato`) e negli
altri dice cosa serve e rimanda alle impostazioni.

La logica di `GmailSyncService.discover` (oggi per un cliente già esistente) si affianca a
una lettura nuova, `GmailSyncService.suggest_customers(*, actor, mesi=12) ->
list[SuggestedCustomer]`: per ogni dominio dei corrispondenti negli ultimi dodici mesi,
escluso il dominio della casella e una lista corta di provider (gmail, outlook, hotmail,
yahoo, icloud, pec), il numero di thread, l'ultimo messaggio e le persone viste
(indirizzo e nome). Nulla viene scritto. L'API espone
`GET /api/gmail/suggerimenti-clienti` e `POST /api/customers/da-suggerimenti` con la
selezione (dominio, nome dell'azienda modificabile, persone da includere), che crea i
clienti e le persone in una transazione e registra un'attività per cliente come farebbe
la creazione a mano. Evento browser `clienti_importati` dalla tabella del middleware
(`POST /api/customers/da-suggerimenti`). Sulla Home, la lista con le caselle sotto la
porta Gmail; la stessa lista in Clienti, come azione «Proponi dalla casella», per chi
collega Gmail più tardi. Test core su una casella registrata (`RecordingTransport` del
sync), test API sulle due rotte, test di pagina sulla lista.

## 6. La fattura consegnata all'assistente (REB-224)

La dropzone della porta accetta un solo PDF e crea il documento con
`POST /api/documents` (`tipo: 'documento'`, titolo il nome del file, `note` che dice
«fattura emessa altrove, da registrare») e la versione con il file. Poi la porta mostra
la consegna: il prompt da copiare, con l'id del documento dentro («Leggi il documento
<id>: è una fattura che ho emesso. Se il cliente non c'è, crealo; compila il profilo
emittente con i miei dati che leggi lì; importala con `import_issued_invoice` con il suo
numero e la sua data, e dimmi cosa hai registrato»), e, se non esiste un token
personale, il `ConnectAgentPanel` accanto. Quando nel registro esiste una fattura con
`pdf_sorgente` uguale a quel documento, la porta dice «Registrata» con il link. Nessun
flag nuovo sul documento: la relazione esiste già nell'import. Test di pagina sul
caricamento e sul prompt; nessuna modifica all'API.

## 7. Fuori da questa spec

La mail al giorno 7 a uno spazio ancora vuoto; il digest per le aziende dell'hub; una
versione della Home per chi entra da mobile; la verifica Google dell'app OAuth
(`PIGROCRM_GOOGLE_APP_UNVERIFIED`), che oggi limita i collegamenti a cento account di
prova e va chiesta prima che le porte Gmail escano dal giro dei primi utenti.

## 8. Decisioni prese qui

- Il resoconto va a tutti gli utenti attivi dello spazio, non solo al proprietario, con
  un interruttore per persona.
- La settimana del resoconto è quella chiusa; il lunedì racconta la settimana prima.
- L'idempotenza è per spazio e settimana ISO, nel database dello spazio, così un cron
  ripetuto o un secondo host non raddoppiano.
- I link della mail portano `?da=digest`: è così che la dashboard di attivazione
  (REB-184) distingue un rientro dalla mail da uno spontaneo.
- `posthog` diventa dipendenza dichiarata di core per l'evento lato server, sul modello
  di `rebase_core.analytics` nell'hub: client spento senza chiave, mai un'eccezione fuori.
