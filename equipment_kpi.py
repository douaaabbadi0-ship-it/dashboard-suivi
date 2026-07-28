# -*- coding: utf-8 -*-
"""
equipment_kpi.py — version Supabase.

Remplace data/equipements.json par la table `equipements`
et data/historique_kpi.json par la table `historique_kpi`.
Signatures de fonctions inchangées : app.py n'a rien à modifier.
"""

import os
from datetime import datetime
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def charger_equipements():
    tous_les_equipements = []
    debut = 0
    taille_lot = 1000

    while True:
        response = (
            supabase.table("equipements")
            .select("*")
            .order("tag")
            .range(debut, debut + taille_lot - 1)
            .execute()
        )
        lot = response.data or []
        tous_les_equipements.extend(lot)

        if len(lot) < taille_lot:
            break

        debut += taille_lot

    return tous_les_equipements


def ajouter_equipement(tag, categorie, zone):
    supabase.table("equipements").upsert(
        {"tag": tag, "categorie": categorie, "zone": zone},
        on_conflict="tag",
    ).execute()
    return charger_equipements()


def calculer_kpi_equipement(tag, jours, heures_periode=168, date=None):
    """
    jours = liste de 7 dicts :
      [{"date": "Lundi", "nb_pannes": 1, "heures_arret": 3.5,
        "cause": "Mécanique" | "Électrique" | "Régulation" | "Process" | None,
        "commentaire": "texte libre" | None}, ...]
    heures_periode = durée totale de la période en heures (168h = 7 jours)
    date = date de la saisie (format "YYYY-MM-DD", venant du champ <input type="date">)
    """
    total_pannes = sum(j.get("nb_pannes", 0) for j in jours)
    total_heures_arret = sum(j.get("heures_arret", 0) for j in jours)

    if total_pannes == 0:
        mttr = 0
        mtbf = heures_periode
    else:
        mttr = total_heures_arret / total_pannes
        mtbf = (heures_periode - total_heures_arret) / total_pannes

    disponibilite = ((heures_periode - total_heures_arret) / heures_periode) * 100 if heures_periode > 0 else 0

    detail_pannes = [
        {
            "jour": j.get("date"),
            "nb_pannes": j.get("nb_pannes", 0),
            "heures_arret": j.get("heures_arret", 0),
            "cause": j.get("cause"),
            "commentaire": j.get("commentaire"),
        }
        for j in jours
        if j.get("nb_pannes", 0) > 0
    ]

    pannes_par_cause = {}
    for j in jours:
        cause = j.get("cause")
        nb = j.get("nb_pannes", 0)
        if cause and nb:
            pannes_par_cause[cause] = pannes_par_cause.get(cause, 0) + nb

    resultat = {
        "tag": tag,
        "date": date,
        "nb_pannes_total": total_pannes,
        "heures_arret_total": round(total_heures_arret, 2),
        "mttr": round(mttr, 2),
        "mtbf": round(mtbf, 2),
        "disponibilite": round(disponibilite, 2),
        "detail_pannes": detail_pannes,
        "pannes_par_cause": pannes_par_cause,
    }

    sauvegarder_historique(resultat)
    return resultat


def sauvegarder_historique(resultat):
    supabase.table("historique_kpi").insert({
        "tag": resultat["tag"],
        "date": resultat["date"],
        "nb_pannes_total": resultat["nb_pannes_total"],
        "heures_arret_total": resultat["heures_arret_total"],
        "mttr": resultat["mttr"],
        "mtbf": resultat["mtbf"],
        "disponibilite": resultat["disponibilite"],
        "detail_pannes": resultat["detail_pannes"],
        "pannes_par_cause": resultat["pannes_par_cause"],
    }).execute()


def trouver_saisie_manuelle(tag, date_debut, date_fin):
    """
    Cherche, dans la table historique_kpi, une saisie manuelle pour `tag`
    dont la date tombe entre date_debut et date_fin (inclus). date_debut /
    date_fin peuvent être des objets date ou datetime.

    S'il y a plusieurs saisies dans la période, retourne la plus récente.
    Retourne None si aucune saisie ne correspond.
    """
    d_debut = date_debut.date() if hasattr(date_debut, "date") else date_debut
    d_fin = date_fin.date() if hasattr(date_fin, "date") else date_fin

    response = (
        supabase.table("historique_kpi")
        .select("*")
        .eq("tag", tag)
        .gte("date", d_debut.isoformat())
        .lte("date", d_fin.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def calculer_kpi_equipements_semaine(interventions_correctives, nb_jours, date_debut=None, date_fin=None):
    """
    Calcule MTTR / MTBF / Disponibilité, par équipement, pour les équipements
    ayant eu au moins une intervention corrective durant la semaine.

    Pour chaque équipement concerné :
    - si une saisie manuelle datée existe pour ce tag ET dans la période
      [date_debut, date_fin], elle est utilisée telle quelle (source = "saisie manuelle") ;
    - sinon, on retombe sur l'estimation automatique basée sur les heures
      réelles des interventions correctives (source = "estimé").
    """
    heures_periode = (nb_jours or 0) * 24
    par_tag = {}

    for item in interventions_correctives:
        tag = item.get("tag_equipement")
        if not tag:
            continue
        heures_item = sum(vals.get("reel", 0) for vals in (item.get("heures") or {}).values())
        if tag not in par_tag:
            par_tag[tag] = {"nb_pannes": 0, "heures_arret": 0.0}
        par_tag[tag]["nb_pannes"] += 1
        par_tag[tag]["heures_arret"] += heures_item

    resultats = []
    for tag, vals in par_tag.items():
        saisie_manuelle = None
        if date_debut and date_fin:
            saisie_manuelle = trouver_saisie_manuelle(tag, date_debut, date_fin)

        if saisie_manuelle:
            resultats.append({
                "tag": tag,
                "nb_pannes": saisie_manuelle.get("nb_pannes_total"),
                "heures_arret": saisie_manuelle.get("heures_arret_total"),
                "mttr": saisie_manuelle.get("mttr"),
                "mtbf": saisie_manuelle.get("mtbf"),
                "disponibilite": saisie_manuelle.get("disponibilite"),
                "source": "saisie manuelle",
                "detail_pannes": saisie_manuelle.get("detail_pannes", []),
                "pannes_par_cause": saisie_manuelle.get("pannes_par_cause", {}),
            })
            continue

        total_pannes = vals["nb_pannes"]
        total_heures_arret = vals["heures_arret"]

        if heures_periode <= 0 or total_pannes == 0:
            mttr = mtbf = disponibilite = None
        else:
            mttr = round(total_heures_arret / total_pannes, 2)
            mtbf = round((heures_periode - total_heures_arret) / total_pannes, 2)
            disponibilite = round(((heures_periode - total_heures_arret) / heures_periode) * 100, 2)

        resultats.append({
            "tag": tag,
            "nb_pannes": total_pannes,
            "heures_arret": round(total_heures_arret, 2),
            "mttr": mttr,
            "mtbf": mtbf,
            "disponibilite": disponibilite,
            "source": "estimé",
        })

    resultats.sort(key=lambda r: r["tag"] or "")
    return resultats