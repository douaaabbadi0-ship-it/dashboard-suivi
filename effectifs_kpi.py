# -*- coding: utf-8 -*-
"""
effectifs_kpi.py
Gestion des effectifs par corps de métier et par ligne de production
(107A / 107B / 107C), utilisés pour le calcul de l'Occupancy Rate.

Version Supabase : les données sont stockées dans la table `effectifs`
(colonnes : ligne, metier, effectif) au lieu de data/effectifs.json.
Les signatures de fonctions sont inchangées pour que app.py n'ait rien
à modifier.
"""

import os
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

LIGNES = ["107A", "107B", "107C"]

# Doit rester aligné avec les clés de CRAFT_COLUMNS dans parser.py
METIERS = ["Mecanicien", "Chaudronnier", "Soudeur", "Electricien", "Instrumentiste", "Autre"]

TEMPS_JOURNALIER_MAROC = 8.8  # heures/jour, temps de travail normal marocain


def _defaut():
    return {ligne: {metier: 0 for metier in METIERS} for ligne in LIGNES}


def charger_effectifs():
    """
    Charge tous les effectifs depuis Supabase, sous la même forme qu'avant :
    { "107A": {"Mecanicien": 6, ...}, "107B": {...}, "107C": {...} }
    Crée les lignes manquantes à 0 si la table est vide ou incomplète.
    """
    response = supabase.table("effectifs").select("*").execute()
    rows = response.data or []

    data = _defaut()
    for row in rows:
        ligne = row["ligne"]
        metier = row["metier"]
        if ligne in data and metier in data[ligne]:
            data[ligne][metier] = row["effectif"]

    # Si la table Supabase est vide (premier lancement), on la seed depuis les valeurs par défaut
    if not rows:
        sauvegarder_effectifs(data)

    return data


def sauvegarder_effectifs(data):
    """
    data : { "107A": {"Mecanicien": 6, ...}, ... }
    Upsert ligne par ligne / métier par métier dans Supabase.
    """
    rows = []
    for ligne in LIGNES:
        ligne_data = data.get(ligne, {metier: 0 for metier in METIERS})
        for metier in METIERS:
            rows.append({
                "ligne": ligne,
                "metier": metier,
                "effectif": int(ligne_data.get(metier, 0) or 0),
            })

    supabase.table("effectifs").upsert(rows, on_conflict="ligne,metier").execute()
    return data


def get_effectifs_ligne(ligne):
    """Retourne le dict {metier: effectif} pour une ligne donnée."""
    data = charger_effectifs()
    return data.get(ligne, {metier: 0 for metier in METIERS})


def mettre_a_jour_ligne(ligne, effectifs_metier):
    """
    Met à jour les effectifs d'une ligne donnée.
    effectifs_metier : dict {metier: int}
    """
    if ligne not in LIGNES:
        raise ValueError(f"Ligne inconnue : {ligne}")

    data = charger_effectifs()
    ligne_data = data.get(ligne, {metier: 0 for metier in METIERS})

    for metier in METIERS:
        if metier in effectifs_metier:
            try:
                val = int(effectifs_metier[metier])
            except (TypeError, ValueError):
                val = 0
            ligne_data[metier] = max(0, val)

    data[ligne] = ligne_data
    return sauvegarder_effectifs(data)