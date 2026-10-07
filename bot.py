import logging
import os
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
import pandas as pd
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Dummy Server Flask per soddisfare il piano Free Web Service di Render
web_app = Flask("")


@web_app.route("/")
def home():
    return "Bot attivo e funzionante!"


def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)


# Logging per debug
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Codici Stazione Viaggiatreno
STAZIONE_BERGAMO = "S01701"
STAZIONE_GRECO = "S01645"
STAZIONE_ALBANO = "S01702"


def get_prossimo_bus(file_csv, ora_riferimento):
    try:
        df = pd.read_csv(file_csv)
        df_disponibili = df[df["partenza"] >= ora_riferimento]
        if not df_disponibili.empty:
            primo = df_disponibili.iloc[0]
            return primo["partenza"], primo["arrivo"]
    except Exception as e:
        logging.error(f"Errore lettura {file_csv}: {e}")
    return None, None


def get_partenze_realtime(id_stazione):
    ora_str = datetime.now().strftime("%a %b %d %Y %H:%M:%S")
    url = f"http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/partenze/{id_stazione}/{ora_str}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logging.error(f"Errore API Viaggiatreno: {e}")
    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Ciao! Scegli la direzione del tuo viaggio:",
        reply_markup=reply_markup,
    )


async def gestisci_andata(update: Update):
    ora_attuale = datetime.now().strftime("%H:%M")
    bus_dep, bus_arr = get_prossimo_bus("bus_brusa_bg.csv", ora_attuale)
    msg = "🟢 **PERCORSO DI ANDATA**\n\n"

    if not bus_dep:
        msg += "❌ Nessun bus disponibile da Brusaporto per oggi."
        await update.callback_query.message.reply_text(
            msg, parse_mode="Markdown"
        )
        return

    msg += f"🚌 **Bus Brusaporto ➔ Bergamo**\n• Partenza: `{bus_dep}` | Arrivo Bergamo: `{bus_arr}`\n\n"

    ora_minima_treno = (
        datetime.strptime(bus_arr, "%H:%M") + timedelta(minutes=7)
    ).strftime("%H:%M")
    partenze_bg = get_partenze_realtime(STAZIONE_BERGAMO)

    treno_trovato = None
    for t in partenze_bg:
        dest = t.get("destinazione", "").upper()
        if "MILANO" in dest or "GRECO" in dest:
            if t.get("orarioPartenzaStr", "") >= ora_minima_treno:
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
        msg += f"🚆 **Treno Bergamo ➔ Milano**\n• {tipo} {num} delle `{treno_trovato.get('orarioPartenzaStr')}`\n• Stato: **{ritardo} min di ritardo** | Binario: `{binario}`\n"
    else:
        msg += "⚠️ Nessun treno per Milano trovato in tempo utile dopo il bus."

    await update.callback_query.message.reply_text(msg, parse_mode="Markdown")


async def gestisci_ritorno(update: Update):
    ora_attuale = datetime.now().strftime("%H:%M")
    partenze_greco = get_partenze_realtime(STAZIONE_GRECO)

    treno_ritorno = None
    for t in partenze_greco:
        dest = t.get("destinazione", "").upper()
        if "BERGAMO" in dest:
            if t.get("orarioPartenzaStr", "") >= ora_attuale:
                treno_ritorno = t
                break

    msg = "🔴 **PERCORSO DI RITORNO**\n\n"

    if not treno_ritorno:
        msg += (
            "❌ Nessun treno diretto a Bergamo trovato in partenza da Greco."
        )
        await update.callback_query.message.reply_text(
            msg, parse_mode="Markdown"
        )
        return

    ritardo = treno_ritorno.get("ritardo", 0)
    ora_partenza_str = treno_ritorno.get("orarioPartenzaStr", "18:00")

    ora_partenza_dt = datetime.strptime(ora_partenza_str, "%H:%M")
    ora_arrivo_bg_dt = ora_partenza_dt + timedelta(minutes=40 + ritardo)
    ora_arrivo_bg_str = ora_arrivo_bg_dt.strftime("%H:%M")

    msg += f"🚆 **Treno Milano Greco ➔ Bergamo**\n• {treno_ritorno.get('compTipologiaTreno', 'Treno')} {treno_ritorno.get('numeroTreno')} delle `{ora_partenza_str}`\n• Ritardo attuale: **{ritardo} min**\n• Arrivo stimato a Bergamo: `{ora_arrivo_bg_str}`\n\n🔀 **OPZIONI DA BERGAMO PER CASA:**\n\n"

    # Opzione A: Treno
    partenze_bg = get_partenze_realtime(STAZIONE_BERGAMO)
    treno_albano = None
    for t in partenze_bg:
        dest = t.get("destinazione", "").upper()
        if "VERONA" in dest or "BRESCIA" in dest or "ALBANO" in dest:
            if t.get("orarioPartenzaStr", "") >= ora_arrivo_bg_str:
                treno_albano = t
                break

    if treno_albano:
        ora_alb_dt = datetime.strptime(
            treno_albano.get("orarioPartenzaStr"), "%H:%M"
        )
        differenza_minuti = int(
            (ora_alb_dt - ora_arrivo_bg_dt).total_seconds() / 60
        )
        msg += f"1️⃣ **Treno Bergamo ➔ Albano:**\n   • Partenza: `{treno_albano.get('orarioPartenzaStr')}` (Margine: **{differenza_minuti} min**)\n"
        if differenza_minuti >= 10:
            msg += "   • ✅ **Fattibile!** 🚗 *Fatti venire a prendere ad Albano.*\n"
        else:
            msg += "   • ❌ **Sconsigliato:** hai meno di 10 minuti per il cambio binario.\n"
    else:
        msg += "1️⃣ **Treno per Albano:** Nessun treno in coincidenza.\n"

    msg += "\n"

    # Opzioni B e C: Bus
    ora_min_bus = (ora_arrivo_bg_dt + timedelta(minutes=5)).strftime("%H:%M")
    b_dep, b_arr = get_prossimo_bus("bus_bg_brusa.csv", ora_min_bus)
    if b_dep:
        msg += f"2️⃣ **Bus Bergamo ➔ Brusaporto:**\n   • Partenza ore `{b_dep}` (Arrivo Brusa: `{b_arr}`)\n\n"
    else:
        msg += "2️⃣ **Bus per Brusaporto:** Nessun bus disponibile.\n\n"

    a_dep, a_arr = get_prossimo_bus("bus_bg_albano.csv", ora_min_bus)
    if a_dep:
        msg += f"3️⃣ **Bus Bergamo ➔ Albano:**\n   • Partenza ore `{a_dep}` (Arrivo Albano: `{a_arr}`) 🚗 *Fatti prendere ad Albano.*\n"
    else:
        msg += "3️⃣ **Bus per Albano:** Nessun bus disponibile.\n"

    await update.callback_query.message.reply_text(msg, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "andata":
        await gestisci_andata(update)
    elif query.data == "ritorno":
        await gestisci_ritorno(update)


if __name__ == "__main__":
    # Avvia il server web su un thread separato
    Thread(target=run_web, daemon=True).start()

    TOKEN = os.environ.get("TELEGRAM_TOKEN", "INSERISCI_QUI_IL_TUO_TOKEN_LOCALE")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot avviato...")
    app.run_polling()