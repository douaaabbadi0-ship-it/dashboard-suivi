# -*- coding: utf-8 -*-
"""
Module d'identification (sans mot de passe) pour l'app Flask.
Chaque utilisateur remplit une fiche d'identification (nom, prenom, email, poste)
au lieu de se connecter avec un compte. Supabase sert uniquement a journaliser
les utilisations (tracabilite), pas a gerer des comptes.
"""
from functools import wraps
from flask import session, redirect, url_for, request
from supabase import create_client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def enregistrer_identification(nom, prenom, email, poste):
    """Stocke les infos de l'utilisateur courant dans la session."""
    session["utilisateur"] = {
        "nom": nom.strip(),
        "prenom": prenom.strip(),
        "email": email.strip(),
        "poste": poste.strip(),
    }


def identification_required(f):
    """Decorateur a mettre sur toute route qui necessite une identification prealable."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "utilisateur" not in session:
            return redirect(url_for("identification", next=request.path))
        return f(*args, **kwargs)
    return decorated


def logger_utilisation(ligne=None, fichier_genere=None):
    """Enregistre une utilisation (generation de rapport) dans Supabase pour tracabilite."""
    utilisateur = session.get("utilisateur")
    if not utilisateur:
        return
    try:
        supabase.table("usage_log").insert({
            "nom": utilisateur["nom"],
            "prenom": utilisateur["prenom"],
            "email": utilisateur["email"],
            "poste": utilisateur["poste"],
            "ligne": ligne,
            "fichier_genere": fichier_genere,
        }).execute()
    except Exception as exc:
        print("ERREUR LOG SUPABASE:", exc)