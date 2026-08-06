# -*- coding: utf-8 -*-
import os
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, send_file, jsonify, session, url_for, redirect
from equipment_kpi import charger_equipements, ajouter_equipement, calculer_kpi_equipement
from effectifs_kpi import charger_effectifs, get_effectifs_ligne, mettre_a_jour_ligne, LIGNES, METIERS
from historique_rapports import sauvegarder_rapport_hebdo, charger_historique_rapports

from parser import parse_daily_report, aggregate_week, compute_kpis_officiels
from pdf_generator import generate_weekly_report
from auth import enregistrer_identification, identification_required, logger_utilisation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def _allowed(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def _json_safe(obj):
    """Convertit les dates en chaines pour la serialisation JSON."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "strftime"):
        return obj.strftime("%d/%m/%Y")
    return obj


@app.route("/identification", methods=["GET", "POST"])
def identification():
    erreur = None
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        prenom = request.form.get("prenom", "").strip()
        email = request.form.get("email", "").strip()
        poste = request.form.get("poste", "").strip()

        if not nom or not prenom or not email or not poste:
            erreur = "Merci de remplir tous les champs."
        else:
            enregistrer_identification(nom, prenom, email, poste)
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)

    return render_template("identification.html", erreur=erreur)


@app.route("/changer-utilisateur")
def changer_utilisateur():
    session.pop("utilisateur", None)
    return redirect(url_for("identification"))


@app.route("/")
@identification_required
def index():
    return render_template("index.html", lignes=LIGNES)


@app.route("/api/generate", methods=["POST"])
@identification_required
def generate():
    files = request.files.getlist("daily_reports")
    if not files:
        return jsonify({"error": "Aucun fichier recu."}), 400

    ligne = request.form.get("ligne") or None
    if ligne and ligne not in LIGNES:
        return jsonify({"error": f"Ligne inconnue : {ligne}"}), 400

    session_id = uuid.uuid4().hex[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    saved_paths = []
    for f in files:
        if not f.filename or not _allowed(f.filename):
            continue
        path = os.path.join(session_dir, f.filename)
        f.save(path)
        saved_paths.append(path)

    if not saved_paths:
        return jsonify({"error": "Aucun fichier .xlsx valide."}), 400

    daily_reports = []
    errors = []
    for path in saved_paths:
        try:
            daily_reports.append(parse_daily_report(path))
        except Exception as exc:
            errors.append(f"{os.path.basename(path)} : {exc}")

    if not daily_reports:
        return jsonify({"error": "Aucun fichier n'a pu etre analyse.", "details": errors}), 422

    week_data = aggregate_week(daily_reports)

    effectifs_metier = get_effectifs_ligne(ligne, session["utilisateur"]["email"]) if ligne else None
    kpis_officiels = compute_kpis_officiels(week_data, effectifs_metier=effectifs_metier)

    # --- Persistance pour le suivi de tendance multi-semaines (page /tendances) ---
    sauvegarder_rapport_hebdo(
        ligne=ligne,
        periode=week_data["periode"],
        kpis=_json_safe(week_data["kpis"]),
        kpis_officiels=_json_safe(kpis_officiels),
        email=session["utilisateur"]["email"],
    )

    output_name = f"rapport_hebdo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    output_path = os.path.join(GENERATED_DIR, output_name)
    generate_weekly_report(week_data, kpis_officiels, output_path, ligne=ligne)

    resultats = {
        "download_url": f"/download/{output_name}",
        "nb_fichiers_traites": len(daily_reports),
        "warnings": errors,
        "kpis": _json_safe(week_data["kpis"]),
        "kpis_officiels": _json_safe(kpis_officiels),
        "periode": _json_safe(week_data["periode"]),
        "ligne": ligne,
    }

    session["dernier_resultat"] = resultats

    logger_utilisation(ligne=ligne, fichier_genere=output_name)

    return jsonify({
        "success": True,
        "redirect": url_for("page_dashboard")
    })


@app.route("/download/<filename>")
@identification_required
def download(filename):
    path = os.path.join(GENERATED_DIR, filename)
    if not os.path.isfile(path):
        return "Fichier introuvable", 404
    return send_file(path, as_attachment=True)


@app.route("/dashboard")
@identification_required
def page_dashboard():
    resultats = session.get("dernier_resultat")
    if not resultats:
        return redirect(url_for("index"))
    return render_template("dashboard.html", resultats=resultats)


@app.route("/tendances")
@identification_required
def page_tendances():
    return render_template("tendances.html", lignes=LIGNES)


@app.route("/api/historique-kpi")
@identification_required
def api_historique_kpi():
    ligne = request.args.get("ligne")
    if not ligne or ligne not in LIGNES:
        return jsonify({"error": "Ligne invalide ou manquante."}), 400
    historique = charger_historique_rapports(ligne, session["utilisateur"]["email"])
    return jsonify(historique)


@app.route("/planning")
@identification_required
def page_planning():
    return render_template("planning.html", lignes=LIGNES)


@app.route("/api/planning")
@identification_required
def api_planning():
    ligne = request.args.get("ligne")
    if not ligne or ligne not in LIGNES:
        return jsonify({"error": "Ligne invalide ou manquante."}), 400

    date_debut = datetime(2026, 6, 22)
    date_aujourdhui = datetime.now()

    historique = charger_historique_rapports(ligne, session["utilisateur"]["email"])

    semaines_generees = set()
    for rapport in historique:
        if rapport.get("periode_debut"):
            semaines_generees.add(str(rapport["periode_debut"])[:10])

    semaines = []
    date_courante = date_debut
    while date_courante <= date_aujourdhui:
        semaine_str = date_courante.strftime("%Y-%m-%d")
        semaines.append({
            "periode_debut": semaine_str,
            "generee": semaine_str in semaines_generees
        })
        date_courante += timedelta(weeks=1)

    return jsonify(semaines)


@app.route("/equipements")
@identification_required
def page_equipements():
    equipements = charger_equipements()
    zones_disponibles = sorted(set(eq["zone"] for eq in equipements))
    return render_template("equipements.html", equipements=equipements, zones_disponibles=zones_disponibles)


@app.route("/api/equipements", methods=["GET"])
@identification_required
def api_liste_equipements():
    data = charger_equipements()
    return jsonify(data)


@app.route("/api/equipements", methods=["POST"])
@identification_required
def api_ajouter_equipement():
    data = request.get_json()
    tag = data.get("tag")
    categorie = data.get("categorie")
    zone = data.get("zone")
    equipements = ajouter_equipement(tag, categorie, zone)
    return jsonify(equipements)


@app.route("/api/kpi-equipement", methods=["POST"])
@identification_required
def api_kpi_equipement():
    data = request.get_json()
    tag = data.get("tag")
    date = data.get("date")
    jours = data.get("jours")
    resultat = calculer_kpi_equipement(tag, jours, date=date)
    return jsonify(resultat)


@app.route("/effectifs")
@identification_required
def page_effectifs():
    effectifs = charger_effectifs(session["utilisateur"]["email"])
    return render_template("effectifs.html", effectifs=effectifs, lignes=LIGNES, metiers=METIERS)


@app.route("/api/effectifs", methods=["GET"])
@identification_required
def api_liste_effectifs():
    return jsonify(charger_effectifs(session["utilisateur"]["email"]))


@app.route("/api/effectifs", methods=["POST"])
@identification_required
def api_sauvegarder_effectifs():
    data = request.get_json() or {}
    ligne = data.get("ligne")
    effectifs_metier = data.get("effectifs", {})

    try:
        result = mettre_a_jour_ligne(ligne, effectifs_metier, session["utilisateur"]["email"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)