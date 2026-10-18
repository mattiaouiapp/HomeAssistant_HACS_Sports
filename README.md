# MMOUi Sports per Home Assistant

Un'unica integrazione HACS per le competizioni che seguo, con i dati di [TheSportsDB](https://www.thesportsdb.com) e di [ESPN](https://www.espn.com):

| Competizione | Fonte | Entità | Dashboard |
| --- | --- | --- | --- |
| **FIA World Endurance Championship** | TheSportsDB, lega [4413](https://www.thesportsdb.com/league/4413) | `*.fia_wec_*` | [`dashboards/fia_wec.yaml`](dashboards/fia_wec.yaml) |
| **Dakar Rally** | TheSportsDB, lega [4447](https://www.thesportsdb.com/league/4447) | `*.dakar_rally_*` | [`dashboards/dakar_rally.yaml`](dashboards/dakar_rally.yaml) |
| **SuperLega** (pallavolo maschile) | TheSportsDB, lega [4544](https://www.thesportsdb.com/league/4544), risultati dal [tabellone live di Lega Volley](https://ww2.legavolley.it/lvc/) | `*.volley_superlega_*` | [`dashboards/superlega.yaml`](dashboards/superlega.yaml) |
| **NBA** (basket) | ESPN, nessuna chiave | `*.nba_*` | [`dashboards/nba.yaml`](dashboards/nba.yaml) |

Ogni competizione è una voce separata dell'integrazione, con il suo dispositivo e le sue opzioni. Gli ID delle entità sono fissi e non dipendono dalla lingua di Home Assistant, quindi le dashboard funzionano ovunque. I nomi sono tradotti in italiano e inglese.

Nel repository c'è anche la mia dashboard completa, [`dashboards/sport.yaml`](dashboards/sport.yaml): oltre alle tre competizioni contiene F1 e calcio (Serie A e Champions League), che arrivano da altre integrazioni. Vedi [Dashboard completa](#dashboard-completa).

## Installazione

### HACS

1. HACS → menu ⋮ → **Repository personalizzati** → aggiungi `https://github.com/mattiaouiapp/HomeAssistant_HACS_Sports`, categoria **Integrazione**.
2. Installa **MMOUi Sports** e riavvia Home Assistant.
3. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → MMOUi Sports**, scegli la competizione.
4. Ripeti il punto 3 per ogni altra competizione.

### Manuale

Copia `custom_components/mmoui_sports` in `<config>/custom_components/` e riavvia.

### Passaggio dalle vecchie integrazioni

Questa integrazione sostituisce `fia_wec`, `dakar_rally` e `volley_serie_a`, che usavano gli stessi ID delle entità. Prima di aggiungerla:

1. **Impostazioni → Dispositivi e servizi**: elimina le vecchie voci FIA WEC, Dakar Rally e Volley Serie A.
2. Togli i vecchi repository da HACS. Se un'integrazione era stata copiata a mano, cancella anche la sua cartella in `<config>/custom_components/` (per esempio `fia_wec`).
3. Riavvia Home Assistant.

Se gli ID nuovi finiscono con `_2` (per esempio `sensor.fia_wec_next_race_2`) e la dashboard mostra "Entity not found", le vecchie entità sono rimaste registrate:

1. **Impostazioni → Entità**, cerca il prefisso (`fia_wec`, `dakar_rally` o `volley_superlega`), seleziona quelle non disponibili o "non più fornite" e **Rimuovi**.
2. Su MMOUi Sports elimina la competizione interessata e riaggiungila con **Add service**: ora prende gli ID giusti.

## Opzioni

Da **Configura** su ogni voce:

| Competizione | Opzioni |
| --- | --- |
| FIA WEC | Prove e qualifiche nel calendario (altrimenti solo le gare) |
| Dakar Rally | Giorni di riposo nel calendario |
| SuperLega | Squadra preferita (aggiunge le entità `*_team_*`), solo la squadra preferita nel calendario |
| NBA | Squadra preferita (aggiunge le entità `*_team_*` e tutta la sua stagione nel calendario), solo la squadra preferita nel calendario |
| WEC, Dakar, SuperLega | Chiave API TheSportsDB |

## Entità

### FIA WEC

| Entità | Tipo | Contenuto |
| --- | --- | --- |
| `sensor.fia_wec_next_race` | timestamp | Partenza della prossima gara. Attributi: circuito, paese, round, poster, mappa del tracciato, sessioni del weekend |
| `sensor.fia_wec_next_session` | timestamp | Prossima sessione (prove libere, qualifiche, Hyperpole, gara) |
| `sensor.fia_wec_last_race` | testo | Ultima gara. Attributi: `results` per classe, `winners`, `standings` |
| `sensor.fia_wec_last_race_winner` | testo | Vincitore assoluto (Hypercar) e un attributo per classe |
| `sensor.fia_wec_races_completed` | numero | Gare disputate, con l'elenco della stagione |
| `binary_sensor.fia_wec_race_weekend` | on/off | Dalla prima sessione del weekend alla fine della gara |
| `binary_sensor.fia_wec_session_live` | in corso | Mentre una sessione con orario confermato è in corso (durata stimata) |
| `calendar.fia_wec_calendar` | calendario | Gare e, se attivo, prove e qualifiche |

### Dakar Rally

| Entità | Tipo | Contenuto |
| --- | --- | --- |
| `sensor.dakar_rally_rally_status` | enum | `upcoming`, `racing`, `rest_day`, `finished`. Attributi: stagione, date, tappe totali e completate, giorni di riposo, tappa e bivacco di oggi, immagini |
| `sensor.dakar_rally_rally_start` | data | Prologo (o prima tappa) |
| `sensor.dakar_rally_next_stage` | data | Prossima tappa: percorso, bivacco, tappa marathon, giorni mancanti |
| `sensor.dakar_rally_current_stage` | testo | Tappa di oggi |
| `sensor.dakar_rally_last_stage` | testo | Ultima tappa corsa: classifiche di tappa e generale quando disponibili, riassunto, video |
| `sensor.dakar_rally_stages_completed` | numero | Tappe completate, con tutto il percorso |
| `binary_sensor.dakar_rally_rally_in_progress` | on/off | Dal prologo all'arrivo, riposi compresi |
| `binary_sensor.dakar_rally_stage_today` | on/off | Nei giorni di tappa |
| `calendar.dakar_rally_calendar` | calendario | Prologo, tappe e (se attivo) giorni di riposo |

### SuperLega

Calendario, squadre e stemmi vengono da TheSportsDB. I risultati, i parziali dei set e i **punteggi in diretta** della giornata in corso vengono dal [tabellone live di Lega Volley](https://ww2.legavolley.it/lvc/), aggiornato ogni 30 secondi: TheSportsDB riceve i risultati con ore o giorni di ritardo e non ha il live. Mentre si gioca, l'integrazione legge solo il tabellone, ogni minuto, e interroga TheSportsDB ogni 10 minuti. Il tabellone chiama le squadre con il nome dello sponsor, quindi le partite vengono abbinate per giornata e città. Viene letta solo la tabella della SuperLega.

| Entità | Tipo | Contenuto |
| --- | --- | --- |
| `sensor.volley_superlega_season` | enum | `preseason`, `regular_season`, `playoffs`, `finished`. Attributi: date, squadre, giornate totali e giocate, partite note/giocate/oggi, immagini |
| `sensor.volley_superlega_standings` | testo | La capolista. Attributo `standings`: punti, partite, vittorie 3-0/3-1 e 3-2, sconfitte 2-3 e 1-3/0-3, set, quoziente set, forma |
| `sensor.volley_superlega_next_round` | numero | Prossima giornata (anche quella in corso oggi), con orari, palazzetti e stemmi |
| `sensor.volley_superlega_last_round` | numero | Ultima giornata, con risultati e parziali dei set |
| `sensor.volley_superlega_next_match` | timestamp | Prossima partita del campionato |
| `sensor.volley_superlega_last_result` | testo | Ultimo risultato, es. `Volley Perugia 3-1 Volley Lube` |
| `sensor.volley_superlega_playoffs` | numero | Partite di playoff giocate. Attributo `series`: le serie con vittorie e partite |
| `binary_sensor.volley_superlega_match_today` | on/off | Nei giorni di partita |
| `binary_sensor.volley_superlega_match_live` | in corso | Dall'inizio della partita all'arrivo del risultato. Attributo `matches`: le partite in corso con `live_score` (set vinti, es. `2-1`) e `live_sets` (punteggio di ogni set, l'ultimo è quello in corso) |
| `calendar.volley_superlega_calendar` | calendario | Tutte le partite, con il punteggio nel titolo una volta giocate |
| `sensor.volley_superlega_team_position` | numero | Posizione della squadra preferita, vuota prima dei primi risultati |
| `sensor.volley_superlega_team_next_match` | timestamp | Prossima partita: avversaria, casa o trasferta, palazzetto |
| `sensor.volley_superlega_team_last_match` | testo | Ultimo punteggio dal lato della squadra, es. `3-1`; attributo `outcome` (`won`/`lost`) |
| `binary_sensor.volley_superlega_team_match_today` | on/off | Quando la squadra gioca oggi |
| `binary_sensor.volley_superlega_team_match_live` | in corso | Mentre la squadra sta giocando |

### NBA

| Entità | Tipo | Contenuto |
| --- | --- | --- |
| `sensor.nba_season` | enum | `preseason`, `regular_season`, `play_in`, `playoffs`, `offseason`. Attributi: stagione, date, partite della notte, partite in corso, logo |
| `sensor.nba_games_today` | numero | Partite della notte. Attributo `games`: orario, squadre, loghi, record, punteggio e stato in diretta (quarto e cronometro), parziali per quarto, migliori marcatori, reti TV, serie playoff |
| `sensor.nba_last_results` | numero | L'ultima notte con partite concluse, con gli stessi dettagli |
| `sensor.nba_next_game` | timestamp | Prossima partita della lega |
| `sensor.nba_east_standings`, `sensor.nba_west_standings` | testo | La prima della conference. Attributo `standings`: posizione, vittorie e sconfitte, percentuale, partite di distacco, serie, ultime 10, casa, trasferta, punti fatti e subiti |
| `binary_sensor.nba_game_live` | in corso | Mentre c'è almeno una partita in corso |
| `calendar.nba_calendar` | calendario | Le partite della settimana e, con la squadra preferita, tutta la sua stagione |
| `sensor.nba_team_next_game` | timestamp | Prossima partita della squadra preferita, o quella in corso con il punteggio |
| `sensor.nba_team_last_game` | testo | Ultimo punteggio dal lato della squadra, es. `114-110`; attributo `outcome` (`won`/`lost`) e migliori marcatori |
| `sensor.nba_team_standing` | numero | Posizione nella conference, vuota prima dell'inizio della regular season |
| `binary_sensor.nba_team_game_today` | on/off | Quando la squadra gioca nella notte |
| `binary_sensor.nba_team_game_live` | in corso | Mentre la squadra sta giocando |

Le giornate NBA seguono la data americana (ora di New York), come le conta la NBA: le partite di "martedì" si giocano in Italia nella notte tra martedì e mercoledì. Gli orari nelle entità e nella dashboard sono quelli locali.

## Dashboard

| File | Contenuto | Richiede |
| --- | --- | --- |
| [`fia_wec.yaml`](dashboards/fia_wec.yaml), [`dakar_rally.yaml`](dashboards/dakar_rally.yaml), [`superlega.yaml`](dashboards/superlega.yaml), [`nba.yaml`](dashboards/nba.yaml) | Una competizione per dashboard | Solo questa integrazione, card native |
| [`sport.yaml`](dashboards/sport.yaml) | La mia dashboard completa: F1, WEC, Dakar, Serie A con Champions League, SuperLega, NBA | Anche [Calcio Live](https://github.com/Bobsilvio/calcio-live) con le sue card (Serie A, Champions League e il Milan), un'integrazione F1 con entità `sensor.f1_*` e [button-card](https://github.com/custom-cards/button-card) |

Per aggiungerne una: **Impostazioni → Plance → Aggiungi plancia → Nuova plancia da zero**, aprila, menu ⋮ → **Modifica plancia** → menu ⋮ → **Editor di configurazione grezza**, e sostituisci il contenuto con il file.

### Dashboard completa

[`sport.yaml`](dashboards/sport.yaml) ha sei viste:

| Vista | Dati da | Entità principali |
| --- | --- | --- |
| F1 | Integrazione F1 con [button-card](https://github.com/custom-cards/button-card) | `sensor.f1_*` |
| WEC | MMOUi Sports | `*.fia_wec_*` |
| Dakar Rally | MMOUi Sports | `*.dakar_rally_*` |
| Calcio | [Calcio Live](https://github.com/Bobsilvio/calcio-live) e [Calcio Live Card](https://github.com/Bobsilvio/calcio-live-card) | vedi sotto |
| SuperLega | MMOUi Sports | `*.volley_superlega_*` |
| NBA | MMOUi Sports | `*.nba_*` |

La vista calcio mostra il Milan, la classifica di Serie A e la Champions League (partite, classifica della fase campionato, tabellone a eliminazione diretta). In Calcio Live servono tre voci:

| Voce Calcio Live | Tipo | Entità usate |
| --- | --- | --- |
| Serie A, squadra AC Milan | Squadra | `sensor.calciolive_next_ita_1_ac_milan` |
| Italian Serie A | Campionato | `sensor.calciolive_classifica_italian_serie_a` |
| UEFA Champions League | Campionato | `sensor.calciolive_all_uefa_champions_league`, `sensor.calciolive_classifica_uefa_champions_league`, `sensor.calciolive_bracket_uefa_champions_league` |

La Champions va da TheSportsDB a Calcio Live perché, con la chiave gratuita, TheSportsDB non ha la classifica e restituisce solo 5 partite su 18 per giornata, mentre Calcio Live (dati ESPN) ha risultati in diretta, classifica e tabellone.

Le viste hanno un'intestazione e sono visibili solo al mio utente (`visible: user`): se usi il file su un altro Home Assistant, togli o cambia quelle righe.

## Chiave API

Vale solo per WEC, Dakar e SuperLega: l'NBA usa l'API pubblica di ESPN, che non richiede chiavi.

TheSportsDB offre una chiave pubblica gratuita (`3`), già impostata come predefinita. Restituisce al massimo 5 eventi per richiesta, quindi l'integrazione ricostruisce le stagioni a pezzi:

- **WEC**: percorre i round uno per uno e, nei weekend con molte sessioni, giorno per giorno;
- **Dakar**: percorre le tappe una per una;
- **SuperLega**: percorre le giornate (6 partite, ne arrivano 5), ricava quali squadre mancano in ogni giornata e cerca la loro partita per nome; durante i playoff segue la prossima e l'ultima partita di ogni squadra.

Il limite di 30 richieste al minuto vale per tutte le competizioni insieme e l'integrazione lo rispetta con una coda comune. Il primo caricamento richiede da uno a due minuti per competizione; poi i dati vengono salvati e si aggiorna solo ciò che non è ancora concluso. Ai riavvii successivi le entità sono subito disponibili e l'aggiornamento avviene in background.

Con una chiave [TheSportsDB Premium](https://www.thesportsdb.com/pricing) ogni stagione arriva con una sola richiesta. La chiave si cambia da **Configura**.

## Aggiornamenti

| Competizione | Normalmente | Più spesso |
| --- | --- | --- |
| FIA WEC | ogni 6 ore | ogni 30 minuti nel weekend di gara, finché non c'è il risultato |
| Dakar Rally | ogni 6 ore | ogni 30 minuti dal giorno prima del prologo a due giorni dopo l'arrivo |
| SuperLega | ogni 6 ore | ogni 10 minuti nei giorni di partita, ogni 2 minuti mentre cerca le partite mancanti |
| NBA | ogni ora | ogni 15 minuti nelle giornate con partite, ogni minuto da un'ora prima della prima palla a due fino all'ultimo risultato |

Le entità legate all'orario (prossima sessione o partita, in corso, oggi) si aggiornano ogni minuto senza richieste aggiuntive.

## Limiti

- TheSportsDB non ha dati in tempo reale per WEC, Dakar e SuperLega: i risultati arrivano a evento concluso e lo stato "in corso" si basa sugli orari. L'NBA invece, da ESPN, ha punteggi in diretta aggiornati ogni minuto.
- **WEC**: quando l'orario di una sessione non è noto, TheSportsDB indica mezzanotte UTC e l'evento è "tutto il giorno" (`time_confirmed: false`); la durata delle sessioni è stimata.
- **Dakar**: niente orari di partenza delle tappe; i risultati sono inseriti a mano su TheSportsDB e spesso mancano.
- **NBA**: le classifiche sono quelle della regular season anche durante play-in e playoff; il tabellone dei playoff non c'è, ma ogni partita riporta lo stato della serie (es. "NY leads series 3-1"). Le partite della lega coprono da ieri a una settimana avanti; la stagione intera è nel calendario solo per la squadra preferita.
- **SuperLega**: la classifica è calcolata dai risultati (3 punti per 3-0 e 3-1, 2 per 3-2, 1 per 2-3; a parità vittorie, poi quoziente set), senza penalizzazioni né quoziente punti. TheSportsDB spesso omette il quarto set nei parziali. Le fasi dei playoff non hanno nome, quindi sono mostrate come serie tra due squadre.

## Esempio di automazione

```yaml
automation:
  - alias: Sport - la mia squadra gioca oggi
    triggers:
      - trigger: state
        entity_id: binary_sensor.volley_superlega_team_match_today
        to: "on"
    actions:
      - action: notify.notify
        data:
          message: >-
            {% set n = 'sensor.volley_superlega_team_next_match' %}
            Volley: {{ 'contro' if state_attr(n, 'home') else 'in casa di' }} {{ state_attr(n, 'opponent') }}
            alle {{ as_timestamp(states(n)) | timestamp_custom('%H:%M') }}.
```
