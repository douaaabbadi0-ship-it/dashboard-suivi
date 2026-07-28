# -*- coding: utf-8 -*-
import os
import re

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "Poste_technique_Sur_SAP.xlsx")

BATCH_SIZE = 500


def clean_zone(text, unite):
    if not text:
        return text
    t = re.sub(r"(?i)^etape de procede\s+", "", text)
    t = re.sub(r"(?i)^unite de |^unite\s+", "", t)
    t = re.sub(re.escape(unite), "", t, flags=re.IGNORECASE).strip()
    return t.strip().title() if t else text.strip().title()


def charger_et_transformer(excel_path):
    if not os.path.isfile(excel_path):
        raise SystemExit(f"❌ Fichier introuvable : {excel_path}")

    df = pd.read_excel(excel_path)
    df.columns = ["code", "designation"] + list(df.columns[2:])
    df["designation"] = df["designation"].fillna("")
    df["code"] = df["code"].astype(str)

    code_to_designation = dict(zip(df["code"], df["designation"]))
    df["depth"] = df["code"].str.count("-") + 1

    equip = df[df["depth"] == 5].copy()
    if equip.empty:
        raise SystemExit("❌ Aucun équipement de niveau 5 trouvé.")

    rows = []
    for _, r in equip.iterrows():
        p = r["code"].split("-")
        unite = p[2] if len(p) > 2 else None
        systeme_code = p[3] if len(p) > 3 else None
        parent_code = "-".join(p[:4]) if len(p) >= 4 else None

        designation_parent = code_to_designation.get(parent_code, systeme_code or "")
        categorie = clean_zone(designation_parent, unite or "")
        libelle = str(r["designation"]).strip()

        rows.append({
            "tag": r["code"],
            "categorie": categorie,
            "zone": categorie,
            "unite": unite,
            "libelle": libelle,
        })

    return rows


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("⚠️  SUPABASE_URL / SUPABASE_KEY introuvables dans .env")

    print(f"📄 Lecture de {EXCEL_PATH} ...")
    rows = charger_et_transformer(EXCEL_PATH)
    print(f"✅ {len(rows)} équipements extraits.")

    unites = sorted(set(r["unite"] for r in rows if r["unite"]))
    print(f"   Unités couvertes ({len(unites)}) : {', '.join(unites)}")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("🚀 Envoi vers Supabase ...")
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        supabase.table("equipements").upsert(batch, on_conflict="tag").execute()
        print(f"   -> lot {i // BATCH_SIZE + 1} : {len(batch)} lignes envoyées")

    print(f"\n🎉 Terminé : {len(rows)} équipements synchronisés.")


if __name__ == "__main__":
    main()