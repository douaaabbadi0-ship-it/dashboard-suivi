# -*- coding: utf-8 -*-
"""
effectifs_kpi.py
Gestion des effectifs par corps de métier et par ligne de production
(107A / 107B / 107C), utilisés pour le calcul de l'Occupancy Rate.

Version Supabase avec cloisonnement par utilisateur : les données sont
stockées dans la table `effectifs` (colonnes : ligne, metier, effectif,
email), avec une contrainte d'unicité sur (ligne, metier, email).
Toutes les fonctions prennent désormais un paramètre `email` obligatoire.
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


def charger_effectifs(email):
    """
    Charge tous les effectifs de l'utilisateur `email` depuis Supabase,
    sous la même forme qu'avant :
    { "107A": {"Mecanicien": 6, ...}, "107B": {...}, "107C": {...} }
    Crée les lignes manquantes à 0 si aucune donnée n'existe pour cet
    utilisateur (premier lancement pour lui).
    """
    if not email:
        raise ValueError("email est requis pour charger les effectifs.")

    response = (
        supabase.table("effectifs")
        .select("*")
        .eq("email", email)
        .execute()
    )
    rows = response.data or []

    data = _defaut()
    for row in rows:
        ligne = row["ligne"]
        metier = row["metier"]
        if ligne in data and metier in data[ligne]:
            data[ligne][metier] = row["effectif"]

    # Si aucune ligne n'existe encore pour cet utilisateur, on seed à 0
    if not rows:
        sauvegarder_effectifs(data, email)

    return data


def sauvegarder_effectifs(data, email):
    """
    data : { "107A": {"Mecanicien": 6, ...}, ... }
    Upsert ligne par ligne / métier par métier dans Supabase, pour
    l'utilisateur `email`.
    """
    if not email:
        raise ValueError("email est requis pour sauvegarder les effectifs.")

    rows = []
    for ligne in LIGNES:
        ligne_data = data.get(ligne, {metier: 0 for metier in METIERS})
        for metier in METIERS:
            rows.append({
                "ligne": ligne,
                "metier": metier,
                "effectif": int(ligne_data.get(metier, 0) or 0),
                "email": email,
            })

    supabase.table("effectifs").upsert(rows, on_conflict="ligne,metier,email").execute()
    return data


def get_effectifs_ligne(ligne, email):
    """Retourne le dict {metier: effectif} pour une ligne donnée et un utilisateur donné."""
    data = charger_effectifs(email)
    return data.get(ligne, {metier: 0 for metier in METIERS})


def mettre_a_jour_ligne(ligne, effectifs_metier, email):
    """
    Met à jour les effectifs d'une ligne donnée, pour l'utilisateur `email`.
    effectifs_metier : dict {metier: int}
    """
    if ligne not in LIGNES:
        raise ValueError(f"Ligne inconnue : {ligne}")
    if not email:
        raise ValueError("email est requis pour mettre à jour les effectifs.")

    data = charger_effectifs(email)
    ligne_data = data.get(ligne, {metier: 0 for metier in METIERS})

    for metier in METIERS:
        if metier in effectifs_metier:
            try:
                val = int(effectifs_metier[metier])
            except (TypeError, ValueError):
                val = 0
            ligne_data[metier] = max(0, val)

    data[ligne] = ligne_data
    return sauvegarder_effectifs(data, email)