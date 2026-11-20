"""Einstiegspunkt für Reifen-Teile.exe (PyInstaller): dasselbe Programm in der Variante „Reifen & Teile“."""
import multiprocessing
import os

os.environ["RSB_VARIANTE"] = "reifen"  # vor dem ersten Import von rsb: Name, Datenordner, Port, Update-Kanal

from start_exe import starten  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    starten()
