"""Einstiegspunkt für die EXE (PyInstaller)."""
import multiprocessing
import sys

from rsb.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.stdout is None or sys.stderr is None:
        # EXE ohne Konsolenfenster: Meldungen in Daten/programm.log schreiben
        import os
        from rsb.datenort import ermitteln
        meldungen = []
        daten = ermitteln(ausgabe=meldungen.append)  # fester Datenordner (übernimmt beim ersten Mal die alten Daten)
        os.environ["RSB_DATEN"] = str(daten)
        daten.mkdir(parents=True, exist_ok=True)
        log = daten / "programm.log"
        if log.exists() and log.stat().st_size > 1_000_000:
            log.replace(log.with_suffix(".log.1"))
        datei = open(log, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or datei
        sys.stderr = sys.stderr or datei
        for m in meldungen:
            print(m)
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(errors="replace")  # Umlaute nie zum Absturz werden lassen
        except (AttributeError, ValueError):
            pass
    main()
