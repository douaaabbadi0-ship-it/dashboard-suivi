# -*- coding: utf-8 -*-
"""
migrate_to_supabase.py

Script à exécuter UNE SEULE FOIS, en local, pour transférer les données
actuelles de data/equipements.json et data/historique_kpi.json vers Supabase.

(effectifs.json n'a pas besoin de ce script : il est déjà seedé via schema.sql,
 vu qu'il n'y a que 18 lignes à insérer à la main.)

Pré-requis :
    pip install supabase --break-system-packages   (ou dans ton venv normalement)

Avant de lancer, remplace SUPABASE_URL et SUPABASE_KEY ci-dessous par tes
vraies valeurs (Project Settings > API sur supabase.com), ou mets-les en
variables d'environnement.

Lancement :
    python migrate_to_supabase.py
"""

import os
import json
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "COLLE_TON_URL_ICI")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "COLLE_TA_CLE_ICI")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EQUIPEMENTS_PATH = os.path.join(BASE_DIR, "data", "equipements.json")
HISTORIQUE_PATH = os.path.join(BASE_DIR, "data", "historique_kpi.json")


def main():
    if "COLLE_" in SUPABASE_URL or "COLLE_" in SUPABASE_KEY:
        raise SystemExit(
            "⚠️  Renseigne SUPABASE_URL et SUPABASE_KEY avant de lancer ce script."
        )

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # --- Migration des équipements ---
    if os.path.isfile(EQUIPEMENTS_PATH):
        with open(EQUIPEMENTS_PATH, "r", encoding="utf-8") as f:
            equipements = json.load(f)

        if equipements:
            result = supabase.table("equipements").upsert(equipements).execute()
            print(f"✅ {len(equipements)} équipements migrés vers Supabase.")
        else:
            print("ℹ️  equipements.json est vide, rien à migrer.")
    else:
        print("ℹ️  Aucun fichier data/equipements.json trouvé, étape ignorée.")

    # --- Migration de l'historique KPI (si des saisies manuelles existent déjà) ---
    if os.path.isfile(HISTORIQUE_PATH):
        with open(HISTORIQUE_PATH, "r", encoding="utf-8") as f:
            historique = json.load(f)

        if historique:
            rows = [
                {
                    "tag": h.get("tag"),
                    "date": h.get("date"),
                    "nb_pannes_total": h.get("nb_pannes_total"),
                    "heures_arret_total": h.get("heures_arret_total"),
                    "mttr": h.get("mttr"),
                    "mtbf": h.get("mtbf"),
                    "disponibilite": h.get("disponibilite"),
                    "detail_pannes": h.get("detail_pannes", []),
                    "pannes_par_cause": h.get("pannes_par_cause", {}),
                }
                for h in historique
            ]
            supabase.table("historique_kpi").insert(rows).execute()
            print(f"✅ {len(rows)} entrées d'historique migrées vers Supabase.")
        else:
            print("ℹ️  historique_kpi.json est vide, rien à migrer.")
    else:
        print("ℹ️  Aucun fichier data/historique_kpi.json trouvé, étape ignorée.")

    print("\n🎉 Migration terminée.")


if __name__ == "__main__":
    main()