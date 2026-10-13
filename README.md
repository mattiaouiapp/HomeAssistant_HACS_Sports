# MMOUi Sports per Home Assistant

Un'unica integrazione HACS per le competizioni che seguo, con i dati di [TheSportsDB](https://www.thesportsdb.com):

| Competizione | Lega TheSportsDB | Entità | Dashboard |
| --- | --- | --- | --- |
| **FIA World Endurance Championship** | [4413](https://www.thesportsdb.com/league/4413) | `*.fia_wec_*` | [`dashboards/fia_wec.yaml`](dashboards/fia_wec.yaml) |
| **Dakar Rally** | [4447](https://www.thesportsdb.com/league/4447) | `*.dakar_rally_*` | [`dashboards/dakar_rally.yaml`](dashboards/dakar_rally.yaml) |
| **SuperLega** (pallavolo maschile) | [4544](https://www.thesportsdb.com/league/4544) | `*.volley_superlega_*` | [`dashboards/superlega.yaml`](dashboards/superlega.yaml) |

Ogni competizione è una voce separata dell'integrazione, con il suo dispositivo e le sue opzioni. Gli ID delle entità sono fissi e non dipendono dalla lingua di Home Assistant, quindi le dashboard funzionano ovunque. I nomi sono tradotti in italiano e inglese.

## Installazione

### HACS

1. HACS → menu ⋮ → **Repository personalizzati** → aggiungi `https://github.com/mattiaouiapp/HomeAssistant_HACS_Sports`, categoria **Integrazione**.
2. Installa **MMOUi Sports** e riavvia Home Assistant.
3. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → MMOUi Sports**, scegli la competizione.
4. Ripeti il punto 3 per ogni altra competizione.

### Manuale

Copia `custom_components/mmoui_sports` in `<config>/custom_components/` e riavvia.

### Passaggio dalle vecchie integrazioni

Questa integrazione sostituisce `fia_wec`, `dakar_rally` e `volley_serie_a`. Rimuovi le vecchie voci e i vecchi repository da HACS prima di aggiungerla: gli ID delle entità sono gli stessi, quindi due integrazioni attive insieme andrebbero in conflitto (Home Assistant aggiungerebbe `_2` agli ID).

## Opzioni

Da **Configura** su ogni voce:

| Competizione | Opzioni |
| --- | --- |
| FIA WEC | Prove e qualifiche nel calendario (altrimenti solo le gare) |
| Dakar Rally | Giorni di riposo nel calendario |
| SuperLega | Squadra preferita (aggiunge le entità `*_team_*`), solo la squadra preferita nel calendario |
| Tutte | Chiave API TheSportsDB |

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
| `binary_sensor.volley_superlega_match_live` | in corso | Dall'inizio della partita all'arrivo del risultato (al massimo 2h30) |
| `calendar.volley_superlega_calendar` | calendario | Tutte le partite, con il punteggio nel titolo una volta giocate |
| `sensor.volley_superlega_team_position` | numero | Posizione della squadra preferita, vuota prima dei primi risultati |
| `sensor.volley_superlega_team_next_match` | timestamp | Prossima partita: avversaria, casa o trasferta, palazzetto |
| `sensor.volley_superlega_team_last_match` | testo | Ultimo punteggio dal lato della squadra, es. `3-1`; attributo `outcome` (`won`/`lost`) |
| `binary_sensor.volley_superlega_team_match_today` | on/off | Quando la squadra gioca oggi |
| `binary_sensor.volley_superlega_team_match_live` | in corso | Mentre la squadra sta giocando |

## Dashboard

| File | Contenuto | Richiede |
| --- | --- | --- |
| [`fia_wec.yaml`](dashboards/fia_wec.yaml), [`dakar_rally.yaml`](dashboards/dakar_rally.yaml), [`superlega.yaml`](dashboards/superlega.yaml) | Una competizione per dashboard | Solo questa integrazione, card native |
| [`sport.yaml`](dashboards/sport.yaml) | La mia dashboard completa: F1, WEC, Dakar, Serie A con Champions League, SuperLega | Anche [Calcio Live](https://github.com/Bobsilvio/calcio-live) con le sue card (Serie A, Champions League e il Milan), un'integrazione F1 con entità `sensor.f1_*` e [button-card](https://github.com/custom-cards/button-card) |

Per aggiungerne una: **Impostazioni → Plance → Aggiungi plancia → Nuova plancia da zero**, aprila, menu ⋮ → **Modifica plancia** → menu ⋮ → **Editor di configurazione grezza**, e sostituisci il contenuto con il file.

## Chiave API

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

Le entità legate all'orario (prossima sessione o partita, in corso, oggi) si aggiornano ogni minuto senza richieste aggiuntive.

## Limiti

- TheSportsDB non ha dati in tempo reale per nessuna delle tre competizioni: i risultati arrivano a evento concluso e lo stato "in corso" si basa sugli orari.
- **WEC**: quando l'orario di una sessione non è noto, TheSportsDB indica mezzanotte UTC e l'evento è "tutto il giorno" (`time_confirmed: false`); la durata delle sessioni è stimata.
- **Dakar**: niente orari di partenza delle tappe; i risultati sono inseriti a mano su TheSportsDB e spesso mancano.
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
