import logging
import os
from datetime import datetime, timedelta
from threading import Thread
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.error import Conflict

from src.bottrasporti.schedules import get_prossimo_bus
from src.bottrasporti.viaggiatreno import get_partenze_realtime
from src.bottrasporti.web import run_web


MESSAGGI_ATTIVI = {}


# Logging per debug
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Codici Stazione Viaggiatreno
STAZIONE_BERGAMO = "S01529"
STAZIONE_GRECO = "S01326"
STAZIONE_ALBANO = "S01702"
FUSO_ORARIO_ITALIA = ZoneInfo("Europe/Rome")


def adesso_in_italia():
    return datetime.now(FUSO_ORARIO_ITALIA)


def orario_partenza(treno):
    orario = treno.get("orarioPartenzaStr")
    if orario:
        return orario

    timestamp = treno.get("partenzaTreno") or treno.get("orarioPartenza")
    if timestamp is not None:
        return datetime.fromtimestamp(
            int(timestamp) / 1000,
            FUSO_ORARIO_ITALIA,
        ).strftime("%H:%M")
    return ""


def minuti_da_mezzanotte(orario):
    ore, minuti = (int(valore) for valore in orario.split(":"))
    return ore * 60 + minuti


def tastiera_indietro():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Indietro", callback_data="indietro")]]
    )


def tastiera_direzione():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟢 ANDATA (Brusa ➔ Greco)", callback_data="andata"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔴 RITORNO (Greco ➔ Brusa)", callback_data="ritorno"
                )
            ],
        ]
    )


def messaggio_scelta():
    ora_attuale = adesso_in_italia().strftime("%d/%m/%Y alle %H:%M")
    return (
        "🚍 *Bot Trasporti*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🕒 *Ora italiana:* `{ora_attuale}`\n\n"
        "👋 *Ciao! Dove vuoi andare?*\n"
        "Scegli il percorso per vedere le coincidenze disponibili:"
    )


async def disabilita_pulsanti(message):
    await message.edit_reply_markup(reply_markup=None)


async def invia_scelta(message):
    precedente = MESSAGGI_ATTIVI.get(message.chat_id)
    if precedente and precedente[0] != message.message_id:
        await disabilita_pulsanti(precedente[1])
    nuovo = await message.reply_text(
        messaggio_scelta(),
        reply_markup=tastiera_direzione(),
        parse_mode="Markdown",
    )
    MESSAGGI_ATTIVI[message.chat_id] = (nuovo.message_id, nuovo)


async def invia_percorso(message, testo):
    nuovo = await message.reply_text(
        testo,
        parse_mode="Markdown",
        reply_markup=tastiera_indietro(),
    )
    MESSAGGI_ATTIVI[message.chat_id] = (nuovo.message_id, nuovo)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await invia_scelta(update.message)


async def gestisci_andata(update: Update):
    ora_attuale = adesso_in_italia().strftime("%H:%M")
    bus_dep, bus_arr = get_prossimo_bus("data/bus_brusa_bg.csv", ora_attuale)
    msg = "🟢 *PERCORSO DI ANDATA*\n━━━━━━━━━━━━━━━━━━\n\n"

    if not bus_dep:
        msg += "❌ *Nessun autobus disponibile da Brusaporto per oggi.*"
        await invia_percorso(update.callback_query.message, msg)
        return

    msg += (
        "🚌 *Autobus Brusaporto ➔ Bergamo*\n"
        f"   ├ Partenza: `{bus_dep}`\n"
        f"   └ Arrivo: `{bus_arr}`\n\n"
    )

    ora_minima_treno = (
        datetime.strptime(bus_arr, "%H:%M") + timedelta(minutes=7)
    ).strftime("%H:%M")
    partenze_bg = get_partenze_realtime(STAZIONE_BERGAMO)

    treno_trovato = None
    for t in partenze_bg:
        dest = t.get("destinazione", "").upper()
        if "MILANO" in dest or "GRECO" in dest:
            if minuti_da_mezzanotte(orario_partenza(t)) >= minuti_da_mezzanotte(
                ora_minima_treno
            ):
                treno_trovato = t
                break

    if treno_trovato:
        ritardo = treno_trovato.get("ritardo", 0)
        num = treno_trovato.get("numeroTreno")
        tipo = treno_trovato.get("compTipologiaTreno", "Treno")
        binario = (
            treno_trovato.get("binarioEffettivoPartenzaDescrizione")
            or treno_trovato.get("binarioProgrammatoPartenzaDescrizione")
            or "-"
        )
        orario_treno = orario_partenza(treno_trovato)
        msg += (
            "🚆 *Treno Bergamo ➔ Milano*\n"
            f"   ├ {tipo} {num} — partenza `{orario_treno}`\n"
            f"   ├ Ritardo: *{ritardo} min*\n"
            f"   └ Binario: `{binario}`\n"
        )
    else:
        msg += "⚠️ *Nessun treno per Milano trovato in tempo utile.*"

    await invia_percorso(update.callback_query.message, msg)


async def gestisci_ritorno(update: Update):
    ora_attuale = adesso_in_italia().strftime("%H:%M")
    partenze_greco = get_partenze_realtime(STAZIONE_GRECO)

    treno_ritorno = None
    for t in partenze_greco:
        dest = t.get("destinazione", "").upper()
        if any(
            destinazione in dest
            for destinazione in ("BERGAMO", "PONTE S.PIETRO", "VERDELLO")
        ):
            if minuti_da_mezzanotte(orario_partenza(t)) >= minuti_da_mezzanotte(
                ora_attuale
            ):
                treno_ritorno = t
                break

    msg = "🔴 *PERCORSO DI RITORNO*\n━━━━━━━━━━━━━━━━━━\n\n"

    if not treno_ritorno:
        msg += (
            "❌ *Nessun treno diretto a Bergamo trovato da Greco.*"
        )
        await invia_percorso(update.callback_query.message, msg)
        return

    ritardo = treno_ritorno.get("ritardo", 0)
    ora_partenza_str = orario_partenza(treno_ritorno) or "18:00"

    ora_partenza_dt = datetime.strptime(ora_partenza_str, "%H:%M")
    ora_arrivo_bg_dt = ora_partenza_dt + timedelta(minutes=40 + ritardo)
    ora_arrivo_bg_str = ora_arrivo_bg_dt.strftime("%H:%M")

    msg += (
        "🚆 *Treno Milano Greco ➔ Bergamo*\n"
        f"   ├ {treno_ritorno.get('compTipologiaTreno', 'Treno')} "
        f"{treno_ritorno.get('numeroTreno')} — partenza `{ora_partenza_str}`\n"
        f"   ├ Ritardo: *{ritardo} min*\n"
        f"   └ Arrivo stimato: `{ora_arrivo_bg_str}`\n\n"
        "🏠 *DA BERGAMO A CASA*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # Opzione A: Treno
    partenze_bg = get_partenze_realtime(STAZIONE_BERGAMO)
    treno_albano = None
    for t in partenze_bg:
        dest = t.get("destinazione", "").upper()
        if any(destinazione in dest for destinazione in ("VERONA", "BRESCIA", "ALBANO")):
            if minuti_da_mezzanotte(orario_partenza(t)) >= minuti_da_mezzanotte(
                ora_arrivo_bg_str
            ):
                treno_albano = t
                break

    if treno_albano:
        ora_alb_dt = datetime.strptime(
            orario_partenza(treno_albano), "%H:%M"
        )
        differenza_minuti = int(
            (ora_alb_dt - ora_arrivo_bg_dt).total_seconds() / 60
        )
        msg += (
            "1️⃣ *Treno Bergamo ➔ Albano*\n"
            f"   └ Partenza: `{orario_partenza(treno_albano)}` "
            f"(margine: *{differenza_minuti} min*)\n"
        )
    else:
        msg += "1️⃣ *Treno per Albano:* nessuna coincidenza disponibile.\n"

    msg += "\n"

    # Opzioni B e C: Bus
    ora_min_bus = (ora_arrivo_bg_dt + timedelta(minutes=5)).strftime("%H:%M")
    b_dep, b_arr = get_prossimo_bus("data/bus_bg_brusa.csv", ora_min_bus)
    if b_dep:
        msg += (
            f"2️⃣ *Autobus Bergamo ➔ Brusaporto*\n"
            f"   └ Partenza: `{b_dep}` · Arrivo: `{b_arr}`\n\n"
        )
    else:
        msg += "2️⃣ *Autobus per Brusaporto:* nessuna corsa disponibile.\n\n"

    a_dep, a_arr = get_prossimo_bus("data/bus_bg_albano.csv", ora_min_bus)
    if a_dep:
        msg += (
            f"3️⃣ *Autobus Bergamo ➔ Albano*\n"
            f"   └ Partenza: `{a_dep}` · Arrivo: `{a_arr}`\n"
        )
    else:
        msg += "3️⃣ *Autobus per Albano:* nessuna corsa disponibile.\n"

    await invia_percorso(update.callback_query.message, msg)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    messaggio_attivo = MESSAGGI_ATTIVI.get(query.message.chat_id)
    if not messaggio_attivo or messaggio_attivo[0] != query.message.message_id:
        await disabilita_pulsanti(query.message)
        await query.answer("Questo menu non è più attivo.", show_alert=True)
        return

    await query.answer()
    await disabilita_pulsanti(query.message)
    if query.data == "andata":
        await gestisci_andata(update)
    elif query.data == "ritorno":
        await gestisci_ritorno(update)
    elif query.data == "indietro":
        await invia_scelta(query.message)


async def error_handler(update, context):
    if isinstance(context.error, Conflict):
        logging.error(
            "Polling Telegram gia attivo: arrestare le altre istanze del bot."
        )
        return
    logging.error("Errore durante la gestione dell'aggiornamento", exc_info=context.error)


if __name__ == "__main__":
    # Avvia il server web su un thread separato
    Thread(target=run_web, daemon=True).start()

    TOKEN = os.environ.get("TELEGRAM_TOKEN", "INSERISCI_QUI_IL_TUO_TOKEN_LOCALE")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)

    print("Bot avviato...")
    app.run_polling(drop_pending_updates=True)