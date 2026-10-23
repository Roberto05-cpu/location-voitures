# donnees_test.py : crée projet.db et la remplit de données de test réalistes.
# Volumes : 4 catégories, 20 véhicules, 50 clients, 120+ locations, 40+ entretiens.
import os
import random
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_BASE = os.path.join(DOSSIER, "projet.db")

NOMS = ["Mbarga", "Ngo Bassa", "Fotso", "Atangana", "Njoya", "Ekane", "Tchoupo", "Bello",
        "Nkoulou", "Tamba", "Kamga", "Essomba", "Mvondo", "Ndzana", "Abena", "Tchinda", "Manga", "Owona"]
PRENOMS = ["Aline", "Paul", "Kevin", "Marie", "Ibrahim", "Sandra", "Rose", "Moussa", "Estelle",
           "Brice", "Nadège", "Hervé", "Clarisse", "Yannick", "Fatima", "Éric", "Ornella", "Landry"]

CATEGORIES = [  # nom, description, prix/jour, supplément chauffeur/jour, caution
    ("Berline économique", "Compacte, sobre et facile à garer : idéale pour la ville.", 25000, 15000, 100000),
    ("Berline confort", "Climatisation, grand coffre et sièges soignés pour les longs trajets.", 40000, 20000, 150000),
    ("4x4 / SUV", "Tout-terrain robuste pour la route de Kribi comme pour les pistes.", 65000, 25000, 300000),
    ("Minibus", "De 9 à 30 places pour mariages, excursions et missions d'entreprise.", 90000, 30000, 250000),
]
# marque, modèle, catégorie (1-4), places, boîte
FLOTTE = [
    ("Toyota", "Yaris", 1, 5, "manuelle"), ("Hyundai", "Accent", 1, 5, "manuelle"),
    ("Kia", "Rio", 1, 5, "manuelle"), ("Suzuki", "Dzire", 1, 5, "manuelle"),
    ("Nissan", "Sunny", 1, 5, "manuelle"),
    ("Toyota", "Camry", 2, 5, "automatique"), ("Hyundai", "Sonata", 2, 5, "automatique"),
    ("Honda", "Accord", 2, 5, "automatique"), ("Kia", "Optima", 2, 5, "automatique"),
    ("Toyota", "Avensis", 2, 5, "manuelle"),
    ("Toyota", "Land Cruiser Prado", 3, 7, "automatique"), ("Toyota", "Hilux", 3, 5, "manuelle"),
    ("Mitsubishi", "Pajero", 3, 7, "automatique"), ("Nissan", "Patrol", 3, 7, "automatique"),
    ("Toyota", "RAV4", 3, 5, "automatique"),
    ("Toyota", "Hiace", 4, 15, "manuelle"), ("Hyundai", "H1", 4, 9, "manuelle"),
    ("Toyota", "Coaster", 4, 30, "manuelle"), ("Mercedes", "Sprinter", 4, 18, "manuelle"),
    ("Nissan", "Urvan", 4, 14, "manuelle"),
]
PREFIXES_IMAGES = {1: "berline", 2: "bercon", 3: "suv", 4: "mini"}


def remplir(db):
    aujourdhui = date.today()

    # --- Catégories ---
    for c in CATEGORIES:
        db.execute("INSERT INTO categories (nom, description, prix_jour, supplement_chauffeur, caution) "
                   "VALUES (?, ?, ?, ?, ?)", c)

    # --- Clients ---
    for i in range(50):
        db.execute("INSERT INTO clients (nom, telephone, permis) VALUES (?, ?, ?)",
                   (f"{random.choice(PRENOMS)} {random.choice(NOMS)}",
                    f"6{random.randint(5, 9)}{random.randint(0, 9999999):07d}",
                    f"CM{100000 + i * 37}"))

    # --- Véhicules, locations et entretiens (construits ensemble pour rester cohérents) ---
    nb_loc = 0
    vehicules_km = {}
    for idx, (marque, modele, cat, places, boite) in enumerate(FLOTTE):
        km = random.randint(25000, 95000)
        curseur = aujourdhui - timedelta(days=random.randint(26, 40))
        prix, supp = CATEGORIES[cat - 1][2], CATEGORIES[cat - 1][3]
        locations = []
        for _ in range(6):                      # 6 locations par véhicule, sans chevauchement
            debut = curseur + timedelta(days=random.randint(0, 5))
            fin = debut + timedelta(days=random.randint(1, 8))
            curseur = fin                      # le suivant peut commencer le jour du retour
            chauffeur = random.random() < 0.35
            jours = (fin - debut).days
            montant = jours * (prix + (supp if chauffeur else 0))
            if fin <= aujourdhui:
                statut = "annulee" if random.random() < 0.08 else "terminee"
            elif debut <= aujourdhui:
                statut = "en_cours"
            else:
                statut = "confirmee" if random.random() < 0.7 else "demandee"
            km_dep = km_ret = None
            if statut == "terminee":
                km_dep, km_ret = km, km + random.randint(60, 220) * jours
                km = km_ret
            elif statut == "en_cours":
                km_dep = km
            locations.append((debut, fin, chauffeur, km_dep, km_ret, montant, statut))
        vehicules_km[idx + 1] = km
        db.execute("INSERT INTO vehicules (immatriculation, marque, modele, categorie_id, places, boite, "
                   "kilometrage, photo, disponible) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (f"LT-{100 + idx * 7:03d}-{random.choice('ABCDEFGHJKLM')}{random.choice('NPQRSTUVWXYZ')}",
                    marque, modele, cat, places, boite, km,
                    f"{PREFIXES_IMAGES[cat]}_{idx % 5 + 1}.jpg", 0 if idx == 19 else 1))
        for debut, fin, chauffeur, km_dep, km_ret, montant, statut in locations:
            ref = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
            db.execute("INSERT INTO locations (reference, vehicule_id, client_id, date_debut, date_fin, "
                       "avec_chauffeur, km_depart, km_retour, montant, statut, date_demande) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (ref, idx + 1, random.randint(1, 50), debut.isoformat(), fin.isoformat(), int(chauffeur),
                        km_dep, km_ret, montant, statut,
                        (debut - timedelta(days=random.randint(2, 15))).isoformat()))
            nb_loc += 1

    # --- Entretiens : une vidange et un autre entretien par véhicule, + vidanges plus anciennes ---
    en_alerte = random.sample(range(1, 20), 5)   # 5 véhicules dépassent 5 000 km depuis la vidange
    for vid, km in vehicules_km.items():
        ecart = random.randint(5200, 8500) if vid in en_alerte else random.randint(400, 4500)
        db.execute("INSERT INTO entretiens (vehicule_id, date, type, cout, kilometrage) VALUES (?, ?, 'vidange', ?, ?)",
                   (vid, (aujourdhui - timedelta(days=ecart // 60)).isoformat(),
                    random.choice([35000, 40000, 45000, 55000]), km - ecart))
        db.execute("INSERT INTO entretiens (vehicule_id, date, type, cout, kilometrage) VALUES (?, ?, ?, ?, ?)",
                   (vid, (aujourdhui - timedelta(days=random.randint(10, 150))).isoformat(),
                    random.choice(["pneus", "revision"]), random.choice([60000, 120000, 180000, 90000]),
                    max(0, km - random.randint(9000, 20000))))
    for vid in random.sample(range(1, 21), 10):   # anciennes vidanges
        db.execute("INSERT INTO entretiens (vehicule_id, date, type, cout, kilometrage) VALUES (?, ?, 'vidange', ?, ?)",
                   (vid, (aujourdhui - timedelta(days=random.randint(200, 400))).isoformat(), 40000,
                    max(0, vehicules_km[vid] - random.randint(22000, 30000))))

    # --- Compte administrateur de test ---
    db.execute("INSERT INTO administrateurs (login, empreinte) VALUES (?, ?)",
               ("admin", generate_password_hash("Admin!2026")))
    db.commit()
    return nb_loc


if __name__ == "__main__":
    random.seed(42)                      # mêmes données à chaque lancement
    if os.path.exists(FICHIER_BASE):
        os.remove(FICHIER_BASE)
    base = sqlite3.connect(FICHIER_BASE)
    base.execute("PRAGMA foreign_keys = ON")
    with open(os.path.join(DOSSIER, "schema.sql"), encoding="utf-8") as f:
        base.executescript(f.read())
    remplir(base)
    for table in ("categories", "vehicules", "clients", "locations", "entretiens", "administrateurs"):
        print(f"{table} : {base.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]} lignes")
    base.close()
