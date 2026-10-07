# botTrasporti

Telegram bot for coordinating the Brusaporto–Bergamo bus connection with
real-time trains from ViaggiaTreno.

## Project layout

- `bot.py`: production entry point used by Render.
- `src/bottrasporti/`: application modules.
- `data/`: bus timetables in CSV format.
- `tests/`: automated tests for timetable selection.

Each timetable row contains `partenza`, `arrivo` and `giorni`. The `giorni`
field uses the official numeric notation: `1` is Monday, through `6` for
Saturday. For example, `12345` means Monday–Friday and `135` means
Monday–Wednesday–Friday.

## Run locally

```bash
pip install -r requirements.txt
python bot.py
```

Run tests with:

```bash
pytest
```
