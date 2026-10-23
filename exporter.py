# exporter.py : sauvegarde toute la base dans export_projet.sql (CREATE TABLE puis INSERT)
import os
import sqlite3

DOSSIER = os.path.dirname(os.path.abspath(__file__))
db = sqlite3.connect(os.path.join(DOSSIER, "projet.db"))
with open(os.path.join(DOSSIER, "export_projet.sql"), "w", encoding="utf-8") as f:
    for ligne in db.iterdump():
        ligne = ligne.replace("DEFAULT 'v_berline_gris.svg'", "DEFAULT 'berline_1.jpg'")
        f.write(ligne + "\n")
db.close()
print("Export terminé : export_projet.sql")
