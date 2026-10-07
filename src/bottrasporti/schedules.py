import csv
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ITALY_TIMEZONE = ZoneInfo("Europe/Rome")


def get_prossimo_bus(file_csv, ora_riferimento, giorno=None):
    giorno = giorno or datetime.now(ITALY_TIMEZONE).date()
    giorno_codice = str(giorno.isoweekday())
    try:
        csv_path = PROJECT_ROOT / file_csv
        with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.DictReader(csv_file))

        required_columns = {"partenza", "arrivo", "giorni"}
        columns = set(rows[0]) if rows else set()
        if not required_columns.issubset(columns):
            missing = ", ".join(sorted(required_columns - columns))
            raise ValueError(f"colonne mancanti: {missing}")

        for row in rows:
            partenza = (row.get("partenza") or "").strip()
            arrivo = (row.get("arrivo") or "").strip()
            giorni = (row.get("giorni") or "").strip()
            if giorno_codice in giorni and partenza >= ora_riferimento and arrivo:
                return partenza, arrivo
    except (OSError, csv.Error, ValueError) as exc:
        logging.error("Errore lettura %s: %s", file_csv, exc)
    return None, None
