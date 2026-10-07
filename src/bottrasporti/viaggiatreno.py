import logging
from datetime import datetime, timezone
from email.utils import format_datetime

import requests


def get_partenze_realtime(id_stazione):
    ora_str = format_datetime(datetime.now(timezone.utc), usegmt=True)
    url = (
        "http://www.viaggiatreno.it/infomobilita/resteasy/"
        f"viaggiatreno/partenze/{id_stazione}/{ora_str}"
    )
    try:
        res = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        res.raise_for_status()
        partenze = res.json()
        if isinstance(partenze, list):
            return partenze
        logging.error("Risposta API non valida per la stazione %s", id_stazione)
    except (requests.RequestException, ValueError) as exc:
        logging.error("Errore API Viaggiatreno: %s", exc)
    return []
