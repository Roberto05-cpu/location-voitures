# Projet 16 : Location de véhicules (RoadDouala)

Application Web de location de véhicules (berlines, 4x4, minibus) avec ou sans chauffeur.
Technologies : Python 3, Flask, SQLite (`sqlite3`), Jinja2, HTML5, CSS, JavaScript.

## Prérequis

- Python 3.10 ou plus récent.
- Le dossier du projet complet, notamment `static/images` et le fichier `projet.db`.

## Installation et lancement (Windows)

Ouvrir PowerShell dans le dossier du projet, puis exécuter :

```
py -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Si la commande `py` n'est pas reconnue, la remplacer par `python`.
Il n'est pas nécessaire d'activer l'environnement virtuel : les commandes ci-dessus utilisent directement son Python.

Quand le serveur indique qu'il est démarré, ouvrir http://127.0.0.1:5000.
Laisser la fenêtre PowerShell ouverte pendant l'utilisation du site ; `Ctrl+C` arrête le serveur.

La base `projet.db`, déjà remplie avec les données de démonstration, est fournie avec le projet. Si elle est absente, la créer une fois depuis le dossier du projet :

```
.\venv\Scripts\python.exe donnees_test.py
```

Cette commande recrée la base et efface donc les éventuelles données déjà présentes. Ne pas l'exécuter si l'on souhaite conserver ces données.

### macOS et Linux

Depuis un terminal ouvert dans le dossier du projet :

```
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python app.py
```

Si `projet.db` est absent, le recréer avec `./venv/bin/python donnees_test.py` (cette commande efface et recrée la base).

## Recréer les données de test

```
.\venv\Scripts\python.exe donnees_test.py  # recrée projet.db (efface d'abord la base existante)
.\venv\Scripts\python.exe exporter.py      # régénère export_projet.sql
```
L'export SQL est une sauvegarde ; le lancement normal du site n'en a pas besoin. Pour réinitialiser la base, utiliser `donnees_test.py` comme indiqué ci-dessus.

Les photos de la flotte sont dans `static/images` : `berline_1.jpg` à `berline_5.jpg`
(berline économique), `bercon_1.jpg` à `bercon_5.jpg` (berline confort),
`suv_1.jpg` à `suv_5.jpg` (4x4 / SUV) et `mini_1.jpg` à `mini_5.jpg` (minibus).

## Compte administrateur de test

- Adresse : http://127.0.0.1:5000/admin/connexion
- Identifiant : `admin`
- Mot de passe : `Admin!2026`

## Pages

| Adresse | Rôle |
|---|---|
| `/` | Accueil, recherche par dates |
| `/vehicules` | Catalogue filtré (catégorie, places, dates), mis à jour par `fetch` |
| `/vehicules/<id>` | Fiche, montant estimé en direct, demande de réservation |
| `/reservation/<code>` | Confirmation (visible juste après la demande) |
| `/suivi` | Suivi avec code de réservation + téléphone |
| `/admin/connexion`, `/admin` | Connexion, tableau de bord et alertes |
| `/admin/locations` | Valider, annuler, départ, retour avec kilométrage |
| `/admin/vehicules` | Flotte : ajout, mise hors service |
| `/admin/entretiens` | Enregistrer les entretiens, alertes de vidange (> 5 000 km) |
| `/admin/statistiques` | Revenu, entretien vs revenu, utilisation, clients fidèles |

## API JSON

| Route | Description |
|---|---|
| `GET /api/vehicules/disponibles?debut=&fin=&categorie=&places=` | Véhicules libres sur la période |
| `GET /api/estimation?vehicule=&debut=&fin=&chauffeur=` | Montant calculé par le serveur + disponibilité |
| `GET /api/statistiques` | Statistiques (réservé à l'administrateur connecté) |

## Règles métier importantes

- **Chevauchement** : deux périodes se chevauchent si `date_debut < fin_existante AND date_fin > debut_existant`.
  Un retour le 10 et un départ le 10 sont donc permis. Seules les locations *confirmées* ou *en cours* bloquent un véhicule ;
  la validation d'une demande est un `UPDATE` unique qui refuse la confirmation en cas de conflit.
- **Montant** : `jours × (tarif + supplément chauffeur)`, toujours calculé sur le serveur.
- **Kilométrage** : retour strictement supérieur au départ ; il met à jour le compteur du véhicule.
- **Statuts** : demandée → confirmée → en cours → terminée (ou annulée).

## Sécurité

Requêtes SQL paramétrées, mots de passe hachés (`generate_password_hash`), toutes les données revérifiées sur le serveur,
modifications et suppressions uniquement en POST avec jeton CSRF, pages d'administration protégées par `connexion_requise`,
contenu échappé par Jinja (aucun `|safe`, aucun `innerHTML`), `debug=False`.
