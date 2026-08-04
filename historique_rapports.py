import os
from datetime import datetime, date
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _vers_iso(valeur):
    """Convertit une date/datetime ou une chaîne dd/mm/yyyy en chaîne ISO yyyy-mm-dd."""
    if valeur is None:
        return None
    if isinstance(valeur, (date, datetime)):
        return valeur.strftime("%Y-%m-%d")
    if isinstance(valeur, str) and "/" in valeur:
        try:
            return datetime.strptime(valeur, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return valeur
    return valeur


def sauvegarder_rapport_hebdo(ligne, periode, kpis, kpis_officiels):
    """
    Enregistre le résultat d'une analyse hebdomadaire pour permettre
    le suivi de tendance multi-semaines (page /tendances).

    ligne : "107A" / "107B" / "107C" (ou None)
    periode : dict avec "debut" et "fin"
    kpis / kpis_officiels : dicts JSON-sérialisables (déjà passés par _json_safe dans app.py)
    """
    supabase.table("historique_rapports").insert({
        "ligne": ligne,
        "periode_debut": _vers_iso(periode.get("debut")),
        "periode_fin": _vers_iso(periode.get("fin")),
        "kpis": kpis,
        "kpis_officiels": kpis_officiels,
    }).execute()


def charger_historique_rapports(ligne, limite=26):
    """
    Retourne la liste des rapports hebdomadaires passés pour une ligne,
    triés du plus ancien au plus récent (pratique pour tracer une courbe),
    limités aux `limite` dernières semaines.
    """
    response = (
        supabase.table("historique_rapports")
        .select("*")
        .eq("ligne", ligne)
        .order("periode_fin", desc=True)
        .limit(limite)
        .execute()
    )
    rows = response.data or []
    rows.sort(key=lambda r: r.get("periode_fin") or "")
    return rows