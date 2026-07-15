# -*- coding: utf-8 -*-
import os
import uuid
from datetime import datetime

from flask import Flask, render_template, request, send_file, jsonify, session, url_for, redirect
from equipment_kpi import charger_equipements, ajouter_equipement, calculer_kpi_equipement
from effectifs_kpi import charger_effectifs, get_effectifs_ligne, mettre_a_jour_ligne, LIGNES, METIERS

from parser import parse_daily_report, aggregate_week, compute_kpis_officiels
from pdf_generator import generate_weekly_report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}

app = Flask(__name__)
app.secret_key = "pfa-107a-jesa-2026"
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def _allowed(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def _json_safe(obj):
    """Convertit les dates en chaînes pour la sérialisation JSON."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "strftime"):
        return obj.strftime("%d/%m/%Y")
    return obj


@app.route("/")
def index():
    return render_template("index.html", lignes=LIGNES)


@app.route("/api/generate", methods=["POST"])
def generate():
    files = request.files.getlist("daily_reports")
    if not files:
        return jsonify({"error": "Aucun fichier reçu."}), 400

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
        return jsonify({"error": "Aucun fichier n'a pu être analysé.", "details": errors}), 422

    week_data = aggregate_week(daily_reports)

    effectifs_metier = get_effectifs_ligne(ligne) if ligne else None
    kpis_officiels = compute_kpis_officiels(week_data, effectifs_metier=effectifs_metier)

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

    return jsonify({
        "success": True,
        "redirect": url_for("page_dashboard")
    })


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(GENERATED_DIR, filename)
    if not os.path.isfile(path):
        return "Fichier introuvable", 404
    return send_file(path, as_attachment=True)


@app.route("/dashboard")
def page_dashboard():
    resultats = session.get("dernier_resultat")
    if not resultats:
        return redirect(url_for("index"))
    return render_template("dashboard.html", resultats=resultats)


@app.route("/equipements")
def page_equipements():
    equipements = charger_equipements()
    zones_disponibles = sorted(set(eq["zone"] for eq in equipements))
    return render_template("equipements.html", equipements=equipements, zones_disponibles=zones_disponibles)


@app.route("/api/equipements", methods=["GET"])
def api_liste_equipements():
    return jsonify(charger_equipements())


@app.route("/api/equipements", methods=["POST"])
def api_ajouter_equipement():
    data = request.get_json()
    tag = data.get("tag")
    categorie = data.get("categorie")
    zone = data.get("zone")
    equipements = ajouter_equipement(tag, categorie, zone)
    return jsonify(equipements)


@app.route("/api/kpi-equipement", methods=["POST"])
def api_kpi_equipement():
    data = request.get_json()
    tag = data.get("tag")
    date = data.get("date")
    jours = data.get("jours")
    resultat = calculer_kpi_equipement(tag, jours, date=date)
    return jsonify(resultat)


@app.route("/effectifs")
def page_effectifs():
    effectifs = charger_effectifs()
    return render_template("effectifs.html", effectifs=effectifs, lignes=LIGNES, metiers=METIERS)


@app.route("/api/effectifs", methods=["GET"])
def api_liste_effectifs():
    return jsonify(charger_effectifs())


@app.route("/api/effectifs", methods=["POST"])
def api_sauvegarder_effectifs():
    data = request.get_json() or {}
    ligne = data.get("ligne")
    effectifs_metier = data.get("effectifs", {})

    try:
        result = mettre_a_jour_ligne(ligne, effectifs_metier)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)