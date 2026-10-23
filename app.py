"""Application Flask : location de véhicules (Projet 16, Technologies Web).

Public : catalogue, disponibilité, demande de réservation, suivi.
Administration : validation, départ/retour, entretiens, alertes, statistiques.
"""
import os
import re
import secrets
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_BASE = os.path.join(DOSSIER, "projet.db")

app = Flask(__name__)
# En production, définir la variable d'environnement SECRET_KEY.
app.secret_key = os.environ.get("SECRET_KEY", "cle-de-demonstration-Theme16-a-changer")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# ---------------------------------------------------------------- constantes
STATUTS = {"demandee": "Demandée", "confirmee": "Confirmée", "en_cours": "En cours",
           "terminee": "Terminée", "annulee": "Annulée"}
TYPES_ENTRETIEN = {"vidange": "Vidange", "pneus": "Pneus", "revision": "Révision"}
PREFIXES_IMAGES = {1: "berline", 2: "bercon", 3: "suv", 4: "mini"}
SEUIL_VIDANGE = 5000        # km entre deux vidanges avant alerte
DUREE_MAX = 60              # durée maximale d'une location, en jours
RE_TEL = re.compile(r"^6[5-9]\d{7}$")
RE_PERMIS = re.compile(r"^[A-Za-z0-9\- ]{5,30}$")
# Un véhicule est occupé par une location confirmée ou en cours.
STATUTS_BLOQUANTS = "('confirmee', 'en_cours')"


# ---------------------------------------------------------------- base de données
def get_db():
    """Ouvre (une fois par requête) la connexion SQLite."""
    if "db" not in g:
        g.db = sqlite3.connect(FICHIER_BASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def fermer_db(_erreur):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------- outils de validation
def lire_date(texte):
    """Convertit 'AAAA-MM-JJ' en date, ou None si invalide."""
    try:
        return date.fromisoformat((texte or "").strip())
    except ValueError:
        return None


def lire_entier(texte, defaut=None):
    try:
        return int(str(texte).strip())
    except (TypeError, ValueError):
        return defaut


def normaliser_tel(texte):
    """Téléphone camerounais : 9 chiffres commençant par 65-69 (préfixe +237 accepté)."""
    t = re.sub(r"[\s.\-]", "", texte or "")
    if t.startswith("+237"):
        t = t[4:]
    elif t.startswith("237") and len(t) == 12:
        t = t[3:]
    return t if RE_TEL.match(t) else None


def verifier_periode(debut, fin):
    """Retourne un message d'erreur si la période est invalide, sinon None."""
    if debut is None or fin is None:
        return "Choisissez une date de départ et une date de retour valides."
    if debut < date.today():
        return "La date de départ ne peut pas être dans le passé."
    if fin <= debut:
        return "Le retour doit avoir lieu après le départ (au moins 1 jour)."
    if (fin - debut).days > DUREE_MAX:
        return f"La durée maximale d'une location est de {DUREE_MAX} jours."
    return None


def calculer_montant(debut, fin, prix_jour, supplement, avec_chauffeur):
    """Montant = nombre de jours × (tarif + supplément chauffeur éventuel). Toujours calculé ici."""
    jours = (fin - debut).days
    return jours, jours * (prix_jour + (supplement if avec_chauffeur else 0))


# ---------------------------------------------------------------- requêtes métier
SQL_VEHICULE = """
    SELECT v.*, c.nom AS categorie, c.prix_jour, c.supplement_chauffeur, c.caution
    FROM vehicules v JOIN categories c ON c.id = v.categorie_id
"""


def lister_vehicules(db, categorie=None, places=1, debut=None, fin=None):
    """Véhicules en service, filtrés. Si des dates sont données, seuls les véhicules libres restent.

    Deux périodes se chevauchent si l'une commence avant la fin de l'autre ET finit après son début :
    date_debut < fin_demandée AND date_fin > debut_demandé. (Retour le 10 / départ le 10 : permis.)
    """
    sql = SQL_VEHICULE + " WHERE v.disponible = 1 AND v.places >= ?"
    params = [places]
    if categorie:
        sql += " AND v.categorie_id = ?"
        params.append(categorie)
    if debut and fin:
        sql += (" AND NOT EXISTS (SELECT 1 FROM locations l WHERE l.vehicule_id = v.id"
                f" AND l.statut IN {STATUTS_BLOQUANTS} AND l.date_debut < ? AND l.date_fin > ?)")
        params += [fin.isoformat(), debut.isoformat()]
    sql += " ORDER BY c.prix_jour, v.marque, v.modele"
    return db.execute(sql, params).fetchall()


def vehicule_libre(db, vehicule_id, debut, fin):
    ligne = db.execute(
        "SELECT 1 FROM locations WHERE vehicule_id = ? AND statut IN " + STATUTS_BLOQUANTS +
        " AND date_debut < ? AND date_fin > ?", (vehicule_id, fin.isoformat(), debut.isoformat())).fetchone()
    return ligne is None


def alertes_vidange(db):
    """Véhicules ayant roulé plus de 5 000 km depuis leur dernière vidange."""
    return db.execute("""
        SELECT v.id, v.immatriculation, v.marque, v.modele, v.kilometrage,
               COALESCE(MAX(e.kilometrage), 0) AS km_vidange,
               v.kilometrage - COALESCE(MAX(e.kilometrage), 0) AS depuis
        FROM vehicules v
        LEFT JOIN entretiens e ON e.vehicule_id = v.id AND e.type = 'vidange'
        GROUP BY v.id HAVING depuis > ? ORDER BY depuis DESC""", (SEUIL_VIDANGE,)).fetchall()


def vehicule_en_dict(v):
    return {"id": v["id"], "immatriculation": v["immatriculation"], "marque": v["marque"],
            "modele": v["modele"], "categorie": v["categorie"], "places": v["places"],
            "boite": v["boite"], "kilometrage": v["kilometrage"], "prix_jour": v["prix_jour"],
            "supplement_chauffeur": v["supplement_chauffeur"], "caution": v["caution"],
            "photo": url_for("static", filename="images/" + v["photo"]),
            "url": url_for("fiche_vehicule", vid=v["id"])}


# ---------------------------------------------------------------- statistiques
def stats_vehicules(db):
    """Revenu, jours loués et coût d'entretien de chaque véhicule (locations terminées)."""
    lignes = db.execute("""
        SELECT v.id, v.immatriculation, v.marque || ' ' || v.modele AS nom,
          COALESCE((SELECT SUM(l.montant) FROM locations l
                    WHERE l.vehicule_id = v.id AND l.statut = 'terminee'), 0) AS revenu,
          COALESCE((SELECT SUM(CAST(julianday(l.date_fin) - julianday(l.date_debut) AS INTEGER))
                    FROM locations l WHERE l.vehicule_id = v.id AND l.statut = 'terminee'), 0) AS jours,
          COALESCE((SELECT SUM(e.cout) FROM entretiens e WHERE e.vehicule_id = v.id), 0) AS entretien
        FROM vehicules v ORDER BY revenu DESC""").fetchall()
    return [dict(l, solde=l["revenu"] - l["entretien"]) for l in lignes]


def stats_utilisation(db, nb_mois=6):
    """Taux d'utilisation de la flotte par mois = jours loués / (véhicules × jours du mois)."""
    nb_vehicules = db.execute("SELECT COUNT(*) FROM vehicules").fetchone()[0] or 1
    locations = db.execute("SELECT date_debut, date_fin FROM locations "
                           "WHERE statut IN ('terminee', 'en_cours')").fetchall()
    aujourdhui = date.today()
    mois_liste = []
    annee, mois = aujourdhui.year, aujourdhui.month
    for _ in range(nb_mois):
        mois_liste.append((annee, mois))
        mois -= 1
        if mois == 0:
            annee, mois = annee - 1, 12
    resultat = []
    for annee, mois in reversed(mois_liste):
        debut_mois = date(annee, mois, 1)
        fin_mois = date(annee + (mois == 12), mois % 12 + 1, 1)   # 1er jour du mois suivant
        jours_loues = 0
        for l in locations:
            d, f = date.fromisoformat(l["date_debut"]), date.fromisoformat(l["date_fin"])
            jours_loues += max(0, (min(f, fin_mois) - max(d, debut_mois)).days)
        total = nb_vehicules * (fin_mois - debut_mois).days
        resultat.append({"mois": f"{mois:02d}/{annee}", "jours_loues": jours_loues,
                         "taux": round(100 * jours_loues / total, 1)})
    return resultat


def stats_fideles(db):
    return [dict(l) for l in db.execute("""
        SELECT c.nom, c.telephone, COUNT(l.id) AS nb_locations, SUM(l.montant) AS total
        FROM clients c JOIN locations l ON l.client_id = c.id
        WHERE l.statut = 'terminee'
        GROUP BY c.id ORDER BY nb_locations DESC, total DESC LIMIT 10""").fetchall()]


def toutes_les_stats(db):
    return {"vehicules": stats_vehicules(db), "utilisation": stats_utilisation(db),
            "fideles": stats_fideles(db)}


# ---------------------------------------------------------------- sécurité
def jeton_csrf():
    """Jeton secret placé dans chaque formulaire POST (protection contre les requêtes forgées)."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def verifier_csrf():
    if request.method == "POST":
        envoye = request.form.get("csrf", "")
        if not envoye or not secrets.compare_digest(envoye, session.get("csrf", "")):
            abort(400)


@app.after_request
def entetes_securite(reponse):
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["X-Frame-Options"] = "DENY"
    reponse.headers["Referrer-Policy"] = "same-origin"
    return reponse


def connexion_requise(fonction):
    """Décorateur : refuse l'accès aux pages d'administration sans connexion."""
    @wraps(fonction)
    def enveloppe(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Connectez-vous pour accéder à l'administration.", "info")
            return redirect(url_for("connexion", suivant=request.path))
        return fonction(*args, **kwargs)
    return enveloppe


# ---------------------------------------------------------------- filtres et variables Jinja
@app.template_filter("fcfa")
def filtre_fcfa(valeur):
    return f"{int(valeur or 0):,}".replace(",", "\u202f") + " FCFA"


@app.template_filter("date_fr")
def filtre_date(texte):
    d = lire_date(texte)
    return d.strftime("%d/%m/%Y") if d else (texte or "")


@app.template_filter("statut")
def filtre_statut(code):
    return STATUTS.get(code, code)


app.jinja_env.globals.update(csrf_token=jeton_csrf, STATUTS=STATUTS, TYPES_ENTRETIEN=TYPES_ENTRETIEN)


@app.context_processor
def variables_communes():
    return {"aujourdhui": date.today().isoformat(), "admin_connecte": bool(session.get("admin_id"))}


# ================================================================ PARTIE PUBLIQUE
@app.route("/")
def accueil():
    db = get_db()
    categories = db.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM vehicules v WHERE v.categorie_id = c.id AND v.disponible = 1) AS nb
        FROM categories c ORDER BY prix_jour""").fetchall()
    vedettes = db.execute(SQL_VEHICULE + """ WHERE v.disponible = 1 AND v.id IN
        (SELECT MIN(id) FROM vehicules WHERE disponible = 1 GROUP BY categorie_id) ORDER BY c.prix_jour""").fetchall()
    chiffres = {"vehicules": db.execute("SELECT COUNT(*) FROM vehicules WHERE disponible = 1").fetchone()[0],
                "clients": db.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
                "locations": db.execute("SELECT COUNT(*) FROM locations WHERE statut = 'terminee'").fetchone()[0]}
    return render_template("accueil.html", categories=categories, vedettes=vedettes, chiffres=chiffres)


@app.route("/vehicules")
def catalogue():
    db = get_db()
    categorie = lire_entier(request.args.get("categorie"))
    places = max(1, lire_entier(request.args.get("places"), 1))
    debut_txt, fin_txt = request.args.get("debut", ""), request.args.get("fin", "")
    debut, fin = lire_date(debut_txt), lire_date(fin_txt)
    dates_ok = False
    if debut_txt or fin_txt:
        erreur = verifier_periode(debut, fin)
        if erreur:
            flash(erreur, "erreur")
        else:
            dates_ok = True
    liste = lister_vehicules(db, categorie, places, debut if dates_ok else None, fin if dates_ok else None)
    categories = db.execute("SELECT id, nom FROM categories ORDER BY prix_jour").fetchall()
    return render_template("vehicules.html", vehicules=liste, categories=categories, categorie=categorie,
                           places=places, debut=debut_txt if dates_ok else "", fin=fin_txt if dates_ok else "",
                           dates_ok=dates_ok)


@app.route("/vehicules/<int:vid>", methods=["GET", "POST"])
def fiche_vehicule(vid):
    db = get_db()
    v = db.execute(SQL_VEHICULE + " WHERE v.id = ?", (vid,)).fetchone()
    if v is None:
        abort(404)
    form = {"nom": "", "telephone": "", "permis": "", "debut": request.args.get("debut", ""),
            "fin": request.args.get("fin", ""), "chauffeur": request.args.get("chauffeur") == "1"}
    erreurs = {}
    if request.method == "POST":
        form = {"nom": " ".join(request.form.get("nom", "").split()),
                "telephone": request.form.get("telephone", "").strip(),
                "permis": " ".join(request.form.get("permis", "").upper().split()),
                "debut": request.form.get("debut", ""), "fin": request.form.get("fin", ""),
                "chauffeur": request.form.get("chauffeur") == "on"}
        # Toutes les données sont revérifiées ici, même si le JavaScript les a déjà contrôlées.
        if not v["disponible"]:
            erreurs["general"] = "Ce véhicule est actuellement hors service."
        if not 2 <= len(form["nom"]) <= 80:
            erreurs["nom"] = "Le nom doit contenir entre 2 et 80 caractères."
        tel = normaliser_tel(form["telephone"])
        if tel is None:
            erreurs["telephone"] = "Numéro invalide : 9 chiffres commençant par 65 à 69 (ex. 677 12 34 56)."
        if not RE_PERMIS.match(form["permis"]):
            erreurs["permis"] = "Numéro de permis invalide (5 à 30 lettres, chiffres ou tirets)."
        debut, fin = lire_date(form["debut"]), lire_date(form["fin"])
        msg = verifier_periode(debut, fin)
        if msg:
            erreurs["dates"] = msg
        elif not vehicule_libre(db, vid, debut, fin):
            erreurs["dates"] = "Ce véhicule est déjà réservé sur tout ou partie de cette période."
        if not erreurs:
            _jours, montant = calculer_montant(debut, fin, v["prix_jour"], v["supplement_chauffeur"],
                                               form["chauffeur"])
            client = db.execute("SELECT id FROM clients WHERE permis = ?", (form["permis"],)).fetchone()
            if client:
                client_id = client["id"]
                db.execute("UPDATE clients SET nom = ?, telephone = ? WHERE id = ?", (form["nom"], tel, client_id))
            else:
                client_id = db.execute("INSERT INTO clients (nom, telephone, permis) VALUES (?, ?, ?)",
                                       (form["nom"], tel, form["permis"])).lastrowid
            for _ in range(5):          # référence aléatoire unique (module secrets)
                reference = secrets.token_hex(4).upper()
                try:
                    db.execute("INSERT INTO locations (reference, vehicule_id, client_id, date_debut, date_fin, "
                               "avec_chauffeur, montant, statut, date_demande) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, 'demandee', ?)",
                               (reference, vid, client_id, debut.isoformat(), fin.isoformat(),
                                int(form["chauffeur"]), montant, date.today().isoformat()))
                    break
                except sqlite3.IntegrityError:
                    reference = None
            if reference is None:
                erreurs["general"] = "Une erreur est survenue, veuillez réessayer."
            else:
                db.commit()
                session["ref_recente"] = reference
                flash("Votre demande est enregistrée. L'agence la confirmera rapidement.", "succes")
                return redirect(url_for("confirmation", reference=reference))
        flash("Le formulaire contient des erreurs : corrigez-les puis réessayez.", "erreur")
    return render_template("vehicule.html", v=v, form=form, erreurs=erreurs)


SQL_LOCATION = """
    SELECT l.*, v.immatriculation, v.marque, v.modele, v.photo, c.nom AS client, c.telephone,
           CAST(julianday(l.date_fin) - julianday(l.date_debut) AS INTEGER) AS jours, cat.caution
    FROM locations l JOIN vehicules v ON v.id = l.vehicule_id JOIN clients c ON c.id = l.client_id
    JOIN categories cat ON cat.id = v.categorie_id """


@app.route("/reservation/<reference>")
def confirmation(reference):
    # La page n'est montrée qu'à la personne qui vient de réserver ; les autres passent par /suivi.
    if session.get("ref_recente") != reference:
        return redirect(url_for("suivi"))
    loc = get_db().execute(SQL_LOCATION + " WHERE l.reference = ?", (reference,)).fetchone()
    if loc is None:
        abort(404)
    return render_template("confirmation.html", loc=loc)


@app.route("/suivi", methods=["GET", "POST"])
def suivi():
    loc, erreur = None, None
    reference, telephone = "", ""
    if request.method == "POST":
        reference = request.form.get("reference", "").strip().upper()
        telephone = request.form.get("telephone", "").strip()
        tel = normaliser_tel(telephone)
        if tel:
            loc = get_db().execute(SQL_LOCATION + " WHERE l.reference = ? AND c.telephone = ?",
                                   (reference, tel)).fetchone()
        if loc is None:
            erreur = "Aucune réservation ne correspond à ce code et à ce numéro de téléphone."
    return render_template("suivi.html", loc=loc, erreur=erreur, reference=reference, telephone=telephone)


# ================================================================ API JSON
@app.route("/api/vehicules/disponibles")
def api_vehicules_disponibles():
    """Véhicules libres entre deux dates (sans dates : tous les véhicules en service)."""
    db = get_db()
    debut_txt, fin_txt = request.args.get("debut", ""), request.args.get("fin", "")
    debut = fin = None
    if debut_txt or fin_txt:
        debut, fin = lire_date(debut_txt), lire_date(fin_txt)
        erreur = verifier_periode(debut, fin)
        if erreur:
            return jsonify({"erreur": erreur}), 400
    liste = lister_vehicules(db, lire_entier(request.args.get("categorie")),
                             max(1, lire_entier(request.args.get("places"), 1)), debut, fin)
    return jsonify({"total": len(liste), "vehicules": [vehicule_en_dict(v) for v in liste]})


@app.route("/api/estimation")
def api_estimation():
    """Montant estimé (calculé sur le serveur) et disponibilité pour un véhicule et une période."""
    v = get_db().execute(SQL_VEHICULE + " WHERE v.id = ?", (lire_entier(request.args.get("vehicule"), 0),)).fetchone()
    if v is None:
        return jsonify({"ok": False, "message": "Véhicule introuvable."}), 404
    debut, fin = lire_date(request.args.get("debut")), lire_date(request.args.get("fin"))
    erreur = verifier_periode(debut, fin)
    if erreur:
        return jsonify({"ok": False, "message": erreur})
    jours, montant = calculer_montant(debut, fin, v["prix_jour"], v["supplement_chauffeur"],
                                      request.args.get("chauffeur") == "1")
    libre = bool(v["disponible"]) and vehicule_libre(get_db(), v["id"], debut, fin)
    return jsonify({"ok": True, "jours": jours, "montant": montant, "caution": v["caution"], "disponible": libre,
                    "message": "" if libre else "Ce véhicule n'est pas libre sur cette période."})


@app.route("/api/statistiques")
def api_statistiques():
    if not session.get("admin_id"):
        return jsonify({"erreur": "Connexion requise."}), 401
    return jsonify(toutes_les_stats(get_db()))


# ================================================================ ADMINISTRATION
@app.route("/admin/connexion", methods=["GET", "POST"])
def connexion():
    if session.get("admin_id"):
        return redirect(url_for("tableau_de_bord"))
    if request.method == "POST":
        login = request.form.get("login", "").strip()
        admin = get_db().execute("SELECT * FROM administrateurs WHERE login = ?", (login,)).fetchone()
        if admin and check_password_hash(admin["empreinte"], request.form.get("mot_de_passe", "")):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_login"] = admin["login"]
            suivant = request.args.get("suivant", "")
            if not (suivant.startswith("/admin") and not suivant.startswith("//")):
                suivant = url_for("tableau_de_bord")
            flash("Bienvenue, " + admin["login"] + ".", "succes")
            return redirect(suivant)
        flash("Identifiant ou mot de passe incorrect.", "erreur")
    return render_template("admin/connexion.html")


@app.route("/admin/deconnexion", methods=["POST"])
def deconnexion():
    session.clear()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("accueil"))


@app.route("/admin")
@connexion_requise
def tableau_de_bord():
    db = get_db()
    compte = lambda sql: db.execute(sql).fetchone()[0]
    chiffres = {"demandes": compte("SELECT COUNT(*) FROM locations WHERE statut = 'demandee'"),
                "en_cours": compte("SELECT COUNT(*) FROM locations WHERE statut = 'en_cours'"),
                "vehicules": compte("SELECT COUNT(*) FROM vehicules WHERE disponible = 1"),
                "hors_service": compte("SELECT COUNT(*) FROM vehicules WHERE disponible = 0")}
    demandes = db.execute(SQL_LOCATION + " WHERE l.statut = 'demandee' ORDER BY l.date_debut LIMIT 6").fetchall()
    aujourdhui = date.today().isoformat()
    departs = db.execute(SQL_LOCATION + " WHERE l.statut = 'confirmee' AND l.date_debut <= ? "
                         "ORDER BY l.date_debut", (aujourdhui,)).fetchall()
    retours = db.execute(SQL_LOCATION + " WHERE l.statut = 'en_cours' AND l.date_fin <= ? "
                         "ORDER BY l.date_fin", (aujourdhui,)).fetchall()
    return render_template("admin/tableau.html", chiffres=chiffres, demandes=demandes, departs=departs,
                           retours=retours, alertes=alertes_vidange(db))


@app.route("/admin/locations")
@connexion_requise
def admin_locations():
    statut = request.args.get("statut", "")
    if statut not in STATUTS:
        statut = ""
    page = max(1, lire_entier(request.args.get("page"), 1))
    par_page = 20
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM locations WHERE (? = '' OR statut = ?)", (statut, statut)).fetchone()[0]
    lignes = db.execute(SQL_LOCATION + """ WHERE (? = '' OR l.statut = ?)
        ORDER BY CASE l.statut WHEN 'demandee' THEN 0 WHEN 'confirmee' THEN 1 WHEN 'en_cours' THEN 2 ELSE 3 END,
                 l.date_debut DESC LIMIT ? OFFSET ?""", (statut, statut, par_page, (page - 1) * par_page)).fetchall()
    km = {r["id"]: r["kilometrage"] for r in db.execute("SELECT id, kilometrage FROM vehicules")}
    return render_template("admin/locations.html", locations=lignes, statut=statut, page=page,
                           pages=max(1, -(-total // par_page)), total=total, km=km)


@app.route("/admin/locations/<int:lid>/valider", methods=["POST"])
@connexion_requise
def valider_location(lid):
    db = get_db()
    # Un seul UPDATE atomique : la confirmation est refusée si un chevauchement existe.
    n = db.execute("""
        UPDATE locations SET statut = 'confirmee'
        WHERE id = ? AND statut = 'demandee'
          AND (SELECT disponible FROM vehicules WHERE id = locations.vehicule_id) = 1
          AND NOT EXISTS (SELECT 1 FROM locations o WHERE o.vehicule_id = locations.vehicule_id
                          AND o.id <> locations.id AND o.statut IN ('confirmee', 'en_cours')
                          AND o.date_debut < locations.date_fin AND o.date_fin > locations.date_debut)""",
                   (lid,)).rowcount
    db.commit()
    if n:
        flash("Réservation confirmée.", "succes")
    else:
        flash("Confirmation impossible : véhicule déjà pris sur cette période, hors service, ou demande déjà traitée.", "erreur")
    return redirect(request.referrer or url_for("admin_locations"))


@app.route("/admin/locations/<int:lid>/annuler", methods=["POST"])
@connexion_requise
def annuler_location(lid):
    db = get_db()
    n = db.execute("UPDATE locations SET statut = 'annulee' WHERE id = ? AND statut IN ('demandee', 'confirmee')",
                   (lid,)).rowcount
    db.commit()
    flash("Réservation annulée." if n else "Seule une demande ou une réservation confirmée peut être annulée.",
          "succes" if n else "erreur")
    return redirect(request.referrer or url_for("admin_locations"))


@app.route("/admin/locations/<int:lid>/depart", methods=["POST"])
@connexion_requise
def depart_location(lid):
    db = get_db()
    loc = db.execute("SELECT l.*, v.kilometrage AS km_vehicule FROM locations l "
                     "JOIN vehicules v ON v.id = l.vehicule_id WHERE l.id = ?", (lid,)).fetchone()
    if loc is None:
        abort(404)
    km = lire_entier(request.form.get("km_depart"))
    if loc["statut"] != "confirmee":
        flash("Seule une réservation confirmée peut partir.", "erreur")
    elif km is None or km < loc["km_vehicule"]:
        flash(f"Kilométrage de départ invalide : il doit être au moins égal au compteur actuel "
              f"({loc['km_vehicule']} km).", "erreur")
    elif db.execute("SELECT 1 FROM locations WHERE vehicule_id = ? AND statut = 'en_cours'",
                    (loc["vehicule_id"],)).fetchone():
        flash("Ce véhicule est déjà en location : enregistrez d'abord son retour.", "erreur")
    else:
        db.execute("UPDATE locations SET statut = 'en_cours', km_depart = ? WHERE id = ?", (km, lid))
        db.commit()
        flash("Départ enregistré.", "succes")
    return redirect(request.referrer or url_for("admin_locations"))


@app.route("/admin/locations/<int:lid>/retour", methods=["POST"])
@connexion_requise
def retour_location(lid):
    db = get_db()
    loc = db.execute("SELECT * FROM locations WHERE id = ?", (lid,)).fetchone()
    if loc is None:
        abort(404)
    km = lire_entier(request.form.get("km_retour"))
    if loc["statut"] != "en_cours":
        flash("Seule une location en cours peut être clôturée.", "erreur")
    elif km is None or km <= loc["km_depart"]:
        flash(f"Le kilométrage de retour doit être supérieur au kilométrage de départ ({loc['km_depart']} km).", "erreur")
    else:
        db.execute("UPDATE locations SET statut = 'terminee', km_retour = ? WHERE id = ?", (km, lid))
        db.execute("UPDATE vehicules SET kilometrage = MAX(kilometrage, ?) WHERE id = ?", (km, loc["vehicule_id"]))
        db.commit()
        flash(f"Retour enregistré : {km - loc['km_depart']} km parcourus.", "succes")
    return redirect(request.referrer or url_for("admin_locations"))


def images_disponibles(categorie_id=None):
    dossier = os.path.join(DOSSIER, "static", "images")
    categories = ([categorie_id] if categorie_id is not None else PREFIXES_IMAGES)
    prefixes = [PREFIXES_IMAGES[categorie] for categorie in categories if categorie in PREFIXES_IMAGES]
    extensions = (".jpg", ".jpeg", ".png", ".webp")
    return sorted(f for f in os.listdir(dossier)
                  if any(f.startswith(prefix + "_") for prefix in prefixes)
                  and f.lower().endswith(extensions))


@app.route("/admin/vehicules", methods=["GET", "POST"])
@connexion_requise
def admin_vehicules():
    db = get_db()
    form, erreurs = {}, {}
    categories = db.execute("SELECT id, nom FROM categories ORDER BY prix_jour").fetchall()
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in
                ("immatriculation", "marque", "modele", "categorie", "places", "boite", "kilometrage", "photo")}
        form["immatriculation"] = form["immatriculation"].upper()
        if not re.match(r"^[A-Z0-9\- ]{4,15}$", form["immatriculation"]):
            erreurs["immatriculation"] = "Immatriculation invalide (ex. LT-123-AB)."
        elif db.execute("SELECT 1 FROM vehicules WHERE immatriculation = ?", (form["immatriculation"],)).fetchone():
            erreurs["immatriculation"] = "Cette immatriculation existe déjà."
        if not 2 <= len(form["marque"]) <= 40:
            erreurs["marque"] = "Marque obligatoire (2 à 40 caractères)."
        if not 1 <= len(form["modele"]) <= 40:
            erreurs["modele"] = "Modèle obligatoire (40 caractères maximum)."
        cat = lire_entier(form["categorie"])
        if not db.execute("SELECT 1 FROM categories WHERE id = ?", (cat,)).fetchone():
            erreurs["categorie"] = "Catégorie inconnue."
        places = lire_entier(form["places"])
        if places is None or not 1 <= places <= 60:
            erreurs["places"] = "Entre 1 et 60 places."
        if form["boite"] not in ("manuelle", "automatique"):
            erreurs["boite"] = "Choisissez la boîte de vitesses."
        km = lire_entier(form["kilometrage"])
        if km is None or km < 0:
            erreurs["kilometrage"] = "Kilométrage positif ou nul."
        if form["photo"] not in images_disponibles(cat):
            erreurs["photo"] = "Choisissez une image correspondant à la catégorie."
        if erreurs:
            flash("Le formulaire contient des erreurs.", "erreur")
        else:
            db.execute("INSERT INTO vehicules (immatriculation, marque, modele, categorie_id, places, boite, "
                       "kilometrage, photo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (form["immatriculation"], form["marque"], form["modele"], cat, places, form["boite"],
                        km, form["photo"]))
            db.commit()
            flash("Véhicule ajouté à la flotte.", "succes")
            return redirect(url_for("admin_vehicules"))
    flotte = db.execute(SQL_VEHICULE + " ORDER BY v.disponible DESC, c.prix_jour, v.marque").fetchall()
    return render_template("admin/vehicules.html", flotte=flotte, categories=categories, form=form,
                           erreurs=erreurs, images=images_disponibles())


@app.route("/admin/vehicules/<int:vid>/service", methods=["POST"])
@connexion_requise
def basculer_service(vid):
    db = get_db()
    v = db.execute("SELECT disponible FROM vehicules WHERE id = ?", (vid,)).fetchone()
    if v is None:
        abort(404)
    if v["disponible"] and db.execute("SELECT 1 FROM locations WHERE vehicule_id = ? AND statut = 'en_cours'",
                                      (vid,)).fetchone():
        flash("Impossible : ce véhicule est actuellement en location.", "erreur")
    else:
        db.execute("UPDATE vehicules SET disponible = 1 - disponible WHERE id = ?", (vid,))
        db.commit()
        flash("Statut du véhicule mis à jour.", "succes")
    return redirect(url_for("admin_vehicules"))


@app.route("/admin/entretiens", methods=["GET", "POST"])
@connexion_requise
def admin_entretiens():
    db = get_db()
    form, erreurs = {}, {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in ("vehicule", "date", "type", "cout", "kilometrage")}
        v = db.execute("SELECT * FROM vehicules WHERE id = ?", (lire_entier(form["vehicule"], 0),)).fetchone()
        if v is None:
            erreurs["vehicule"] = "Choisissez un véhicule."
        d = lire_date(form["date"])
        if d is None or d > date.today():
            erreurs["date"] = "Date invalide (pas dans le futur)."
        if form["type"] not in TYPES_ENTRETIEN:
            erreurs["type"] = "Type d'entretien inconnu."
        cout = lire_entier(form["cout"])
        if cout is None or cout < 0:
            erreurs["cout"] = "Coût positif ou nul, en FCFA."
        km = lire_entier(form["kilometrage"])
        if km is None or km < 0:
            erreurs["kilometrage"] = "Kilométrage positif ou nul."
        elif v is not None and km > v["kilometrage"]:
            erreurs["kilometrage"] = f"Supérieur au compteur actuel du véhicule ({v['kilometrage']} km)."
        if erreurs:
            flash("Le formulaire contient des erreurs.", "erreur")
        else:
            db.execute("INSERT INTO entretiens (vehicule_id, date, type, cout, kilometrage) VALUES (?, ?, ?, ?, ?)",
                       (v["id"], d.isoformat(), form["type"], cout, km))
            db.commit()
            flash("Entretien enregistré.", "succes")
            return redirect(url_for("admin_entretiens"))
    entretiens = db.execute("""SELECT e.*, v.immatriculation, v.marque, v.modele FROM entretiens e
        JOIN vehicules v ON v.id = e.vehicule_id ORDER BY e.date DESC, e.id DESC LIMIT 40""").fetchall()
    vehicules = db.execute("SELECT id, immatriculation, marque, modele, kilometrage FROM vehicules "
                           "ORDER BY marque, modele").fetchall()
    return render_template("admin/entretiens.html", entretiens=entretiens, vehicules=vehicules,
                           alertes=alertes_vidange(db), form=form, erreurs=erreurs, seuil=SEUIL_VIDANGE)


@app.route("/admin/statistiques")
@connexion_requise
def admin_statistiques():
    return render_template("admin/statistiques.html", stats=toutes_les_stats(get_db()))


# ---------------------------------------------------------------- erreurs
@app.errorhandler(404)
def page_introuvable(_e):
    return render_template("404.html"), 404


@app.errorhandler(400)
def requete_invalide(_e):
    return render_template("erreur.html", code=400, titre="Requête refusée",
                           message="Le formulaire a expiré ou n'est pas valide. Revenez en arrière et réessayez."), 400


@app.errorhandler(500)
def erreur_serveur(_e):
    return render_template("erreur.html", code=500, titre="Erreur du serveur",
                           message="Un problème est survenu de notre côté. Réessayez dans un instant."), 500


if __name__ == "__main__":
    if not os.path.exists(FICHIER_BASE):
        print("Base absente : lancez d'abord  python donnees_test.py")
    app.run(debug=False)    # debug=False dans la version rendue
