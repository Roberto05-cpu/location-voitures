-- schema.sql : création des tables (Projet 16 : location de véhicules)
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS entretiens;
DROP TABLE IF EXISTS locations;
DROP TABLE IF EXISTS clients;
DROP TABLE IF EXISTS vehicules;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS administrateurs;

-- Catégories de véhicules et leurs tarifs (en FCFA)
CREATE TABLE categories (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nom                  TEXT    NOT NULL UNIQUE,
    description          TEXT    NOT NULL DEFAULT '',
    prix_jour            INTEGER NOT NULL CHECK (prix_jour > 0),
    supplement_chauffeur INTEGER NOT NULL CHECK (supplement_chauffeur >= 0),
    caution              INTEGER NOT NULL CHECK (caution >= 0)
);

-- La flotte
CREATE TABLE vehicules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    immatriculation  TEXT    NOT NULL UNIQUE,
    marque           TEXT    NOT NULL,
    modele           TEXT    NOT NULL,
    categorie_id     INTEGER NOT NULL REFERENCES categories(id),
    places           INTEGER NOT NULL CHECK (places BETWEEN 1 AND 60),
    boite            TEXT    NOT NULL CHECK (boite IN ('manuelle', 'automatique')),
    kilometrage      INTEGER NOT NULL CHECK (kilometrage >= 0),
    photo            TEXT    NOT NULL DEFAULT 'berline_1.jpg',
    disponible       INTEGER NOT NULL DEFAULT 1 CHECK (disponible IN (0, 1))  -- 0 = hors service
);

CREATE TABLE clients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nom        TEXT NOT NULL,
    telephone  TEXT NOT NULL,
    permis     TEXT NOT NULL UNIQUE
);

-- Locations : statut = demandee -> confirmee -> en_cours -> terminee (ou annulee)
CREATE TABLE locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reference       TEXT    NOT NULL UNIQUE,           -- code de suivi difficile à deviner
    vehicule_id     INTEGER NOT NULL REFERENCES vehicules(id),
    client_id       INTEGER NOT NULL REFERENCES clients(id),
    date_debut      TEXT    NOT NULL,                  -- format AAAA-MM-JJ
    date_fin        TEXT    NOT NULL,                  -- jour de retour
    avec_chauffeur  INTEGER NOT NULL DEFAULT 0 CHECK (avec_chauffeur IN (0, 1)),
    km_depart       INTEGER CHECK (km_depart IS NULL OR km_depart >= 0),
    km_retour       INTEGER,
    montant         INTEGER NOT NULL CHECK (montant >= 0),
    statut          TEXT    NOT NULL DEFAULT 'demandee'
                    CHECK (statut IN ('demandee', 'confirmee', 'en_cours', 'terminee', 'annulee')),
    date_demande    TEXT    NOT NULL,
    CHECK (date_fin > date_debut),
    CHECK (km_retour IS NULL OR (km_depart IS NOT NULL AND km_retour > km_depart))
);
CREATE INDEX idx_locations_vehicule ON locations (vehicule_id, date_debut, date_fin);

CREATE TABLE entretiens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicule_id  INTEGER NOT NULL REFERENCES vehicules(id),
    date         TEXT    NOT NULL,
    type         TEXT    NOT NULL CHECK (type IN ('vidange', 'pneus', 'revision')),
    cout         INTEGER NOT NULL CHECK (cout >= 0),
    kilometrage  INTEGER NOT NULL CHECK (kilometrage >= 0)
);

CREATE TABLE administrateurs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    login     TEXT NOT NULL UNIQUE,
    empreinte TEXT NOT NULL
);
