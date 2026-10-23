// main.js : menu, vérification des formulaires, estimation du montant et catalogue dynamique (fetch).
(function () {
  "use strict";

  // ---------- outils ----------
  function el(balise, classe, texte) {            // création d'élément SANS innerHTML (pas d'injection)
    const e = document.createElement(balise);
    if (classe) e.className = classe;
    if (texte !== undefined) e.textContent = texte;
    return e;
  }
  function fcfa(n) { return Number(n).toLocaleString("fr-FR").replace(/\u202f|\u00a0/g, " ") + " FCFA"; }

  // ---------- menu mobile ----------
  const burger = document.getElementById("burger");
  const menu = document.getElementById("menu");
  if (burger && menu) {
    burger.addEventListener("click", function () {
      const ouvert = menu.classList.toggle("ouvert");
      burger.setAttribute("aria-expanded", ouvert ? "true" : "false");
    });
  }

  // ---------- confirmation avant une action sensible ----------
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (ev) {
      if (!window.confirm(f.dataset.confirm)) ev.preventDefault();
    });
  });

  // ---------- vérification des formulaires (le serveur revérifie toujours) ----------
  function telValide(txt) {
    let t = txt.replace(/[\s.\-]/g, "");
    if (t.startsWith("+237")) t = t.slice(4); else if (t.startsWith("237") && t.length === 12) t = t.slice(3);
    return /^6[5-9]\d{7}$/.test(t);
  }
  function erreurChamp(champ, form) {
    const v = champ.value.trim();
    switch (champ.dataset.regle) {
      case "nom": return v.length >= 2 && v.length <= 80 ? "" : "Le nom doit contenir entre 2 et 80 caractères.";
      case "tel": return telValide(v) ? "" : "Numéro invalide : 9 chiffres commençant par 65 à 69 (ex. 677 12 34 56).";
      case "permis": return /^[A-Za-z0-9\- ]{5,30}$/.test(v) ? "" : "Numéro de permis invalide (5 à 30 lettres, chiffres ou tirets).";
      case "requis": return v ? "" : "Ce champ est obligatoire.";
      case "entier": return /^\d+$/.test(v) ? "" : "Entrez un nombre entier positif.";
      case "date-debut":
        if (!v) return "Choisissez la date de départ.";
        return v < form.dataset.aujourdhui ? "La date de départ ne peut pas être dans le passé." : "";
      case "date-fin": {
        const debut = form.querySelector('[data-regle="date-debut"]');
        if (!v) return "Choisissez la date de retour.";
        return debut && debut.value && v <= debut.value ? "Le retour doit avoir lieu après le départ." : "";
      }
      default: return "";
    }
  }
  function afficherErreur(champ, message) {
    const bloc = champ.closest(".champ");
    if (!bloc) return;
    let p = bloc.querySelector(".erreur-champ");
    if (!p && message) { p = el("p", "erreur-champ"); p.setAttribute("role", "alert"); bloc.appendChild(p); }
    if (p) p.textContent = message;
    bloc.classList.toggle("invalide", Boolean(message));
    champ.setAttribute("aria-invalid", message ? "true" : "false");
  }
  document.querySelectorAll("form[data-valider]").forEach(function (form) {
    const champs = form.querySelectorAll("[data-regle]");
    champs.forEach(function (c) {
      c.addEventListener("blur", function () { afficherErreur(c, erreurChamp(c, form)); });
      c.addEventListener("input", function () { if (c.closest(".champ.invalide")) afficherErreur(c, erreurChamp(c, form)); });
    });
    form.addEventListener("submit", function (ev) {
      let premier = null;
      champs.forEach(function (c) {
        const m = erreurChamp(c, form);
        afficherErreur(c, m);
        if (m && !premier) premier = c;
      });
      if (premier) { ev.preventDefault(); premier.focus(); }
    });
  });

  // ---------- fiche véhicule : montant estimé en direct (fetch sur /api/estimation) ----------
  const formResa = document.getElementById("form-reservation");
  if (formResa) {
    const resume = document.getElementById("resume");
    const debut = formResa.elements.debut, fin = formResa.elements.fin, chauffeur = formResa.elements.chauffeur;
    let minuteur = null, numero = 0;
    function majResume() {
      if (!debut.value || !fin.value) return;
      const moi = ++numero;
      const q = new URLSearchParams({ vehicule: formResa.dataset.vehicule, debut: debut.value, fin: fin.value,
                                      chauffeur: chauffeur.checked ? "1" : "0" });
      fetch("/api/estimation?" + q.toString())
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (moi !== numero) return;                      // une réponse plus récente existe
          resume.replaceChildren();
          resume.classList.toggle("indisponible", !(d.ok && d.disponible));
          if (!d.ok || !d.disponible) { resume.appendChild(el("p", "", d.message)); return; }
          const l1 = el("div", "ligne-resume"); l1.append(el("span", "", "Durée"), el("strong", "", d.jours + (d.jours > 1 ? " jours" : " jour")));
          const l2 = el("div", "ligne-resume"); l2.append(el("span", "", "Caution (remboursable)"), el("strong", "", fcfa(d.caution)));
          resume.append(l1, l2, el("div", "total", fcfa(d.montant)));
        })
        .catch(function () { resume.textContent = "Estimation momentanément indisponible."; });
    }
    [debut, fin, chauffeur].forEach(function (c) {
      c.addEventListener("change", function () { clearTimeout(minuteur); minuteur = setTimeout(majResume, 150); });
    });
    // Le départ choisi impose le minimum du retour.
    debut.addEventListener("change", function () { if (debut.value) fin.min = debut.value; });
    majResume();
  }

  // ---------- catalogue : filtres sans rechargement (fetch sur /api/vehicules/disponibles) ----------
  const filtres = document.getElementById("filtres");
  const zone = document.getElementById("resultats");
  if (filtres && zone) {
    const compteur = document.getElementById("compteur");
    const alerte = document.getElementById("erreur-filtres");
    function carte(v, debut, fin) {
      const a = el("article", "carte-vehicule");
      const visuel = el("div", "visuel"); const img = el("img"); img.src = v.photo; img.alt = v.marque + " " + v.modele;
      img.width = 400; img.height = 200; img.loading = "lazy"; visuel.appendChild(img);
      const corps = el("div", "corps");
      const plaque = el("span", "plaque"); plaque.appendChild(el("span", "", v.immatriculation));
      const tags = el("div", "etiquettes");
      [v.categorie, v.places + " places", v.boite].forEach(function (t) { tags.appendChild(el("span", "etiquette", t)); });
      const prix = el("p", "prix", fcfa(v.prix_jour) + " "); prix.appendChild(el("small", "", "/ jour"));
      const lien = el("a", "btn btn-secondaire", "Voir et réserver");
      lien.href = v.url + (debut && fin ? "?debut=" + encodeURIComponent(debut) + "&fin=" + encodeURIComponent(fin) : "");
      corps.append(el("h3", "", v.marque + " " + v.modele), plaque, tags, prix, lien);
      a.append(visuel, corps);
      return a;
    }
    function charger() {
      const q = new URLSearchParams(new FormData(filtres));
      [...q.keys()].forEach(function (k) { if (!q.get(k) || k === "csrf") q.delete(k); });
      history.replaceState(null, "", "?" + q.toString());
      fetch("/api/vehicules/disponibles?" + q.toString())
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          alerte.textContent = "";
          if (!res.ok) { alerte.textContent = res.d.erreur; return; }
          zone.replaceChildren();
          const n = res.d.total;
          compteur.textContent = n + (n > 1 ? " véhicules trouvés" : " véhicule trouvé");
          if (n === 0) {
            const vide = el("div", "vide"); vide.append(el("h3", "", "Aucun véhicule libre"),
              el("p", "", "Essayez d'autres dates, une autre catégorie ou moins de places."));
            zone.appendChild(vide);
          } else {
            res.d.vehicules.forEach(function (v) { zone.appendChild(carte(v, q.get("debut"), q.get("fin"))); });
          }
        })
        .catch(function () { alerte.textContent = "Impossible de charger les véhicules. Réessayez."; });
    }
    filtres.addEventListener("change", charger);
    filtres.addEventListener("submit", function (ev) { ev.preventDefault(); charger(); });
  }
})();
