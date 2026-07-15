# -*- coding: utf-8 -*-
"""
pdf_generator.py
Génère le rapport hebdomadaire au format PDF avec reportlab.
"""

import os
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)

from equipment_kpi import calculer_kpi_equipements_semaine

NAVY = colors.HexColor("#1E2761")
ICE_BLUE = colors.HexColor("#CADCFC")
GREY = colors.HexColor("#6B6B6B")
LIGHT_BG = colors.HexColor("#F4F6FB")

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], textColor=NAVY, fontSize=22, spaceAfter=6)
h2_style = ParagraphStyle("H2Custom", parent=styles["Heading2"], textColor=NAVY, spaceBefore=14, spaceAfter=8)
body_style = ParagraphStyle("BodyCustom", parent=styles["Normal"], fontSize=10, leading=14)
muted_style = ParagraphStyle("Muted", parent=styles["Normal"], fontSize=9, textColor=GREY)


def _chart_heures_par_corps(heures_semaine, tmpdir):
    crafts = list(heures_semaine.keys())
    estimes = [heures_semaine[c]["estime"] for c in crafts]
    reels = [heures_semaine[c]["reel"] for c in crafts]

    fig, ax = plt.subplots(figsize=(6.5, 3.2), dpi=150)
    x = range(len(crafts))
    w = 0.35
    ax.bar([i - w / 2 for i in x], estimes, width=w, label="Estimé", color="#CADCFC")
    ax.bar([i + w / 2 for i in x], reels, width=w, label="Réel", color="#1E2761")
    ax.set_xticks(list(x))
    ax.set_xticklabels(crafts, fontsize=8)
    ax.set_ylabel("Heures", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = os.path.join(tmpdir, "chart_heures.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _kpi_table(kpis, kpis_officiels):
    occ = kpis_officiels.get("occupancy_rate")
    occ_global = occ.get("global") if occ else None
    occ_str = f"{occ_global}%" if occ_global is not None else "Non disponible (ligne ou effectifs non configurés)"

    data = [
        ["Indicateur", "Valeur"],
        ["Taux d'exécution (Schedule Compliance)",
         f"{kpis['taux_execution']}%" if kpis['taux_execution'] is not None else "N/A"],
        ["Efficacité temps (MH réalisé / MH planifié)",
         f"{kpis['efficacite_temps']}%" if kpis['efficacite_temps'] is not None else "N/A"],
        ["OT planifiés", str(kpis["total_planifie"])],
        ["OT non planifiés", str(kpis["total_non_planifie"])],
        ["MTTR approché (correctifs)",
         f"{kpis_officiels['mttr_approx_heures']} h" if kpis_officiels['mttr_approx_heures'] is not None else "N/A"],
        ["Rate of Rework", "Non disponible (données absentes)"],
        ["WOs in Backlog", "Non disponible (données absentes)"],
        ["WOs with Non-Compliance", "Non disponible (données absentes)"],
        ["Occupancy rate", occ_str],
    ]

    table = Table(data, colWidths=[10 * cm, 6 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]))
    return table


def _occupancy_detail_section(kpis_officiels, ligne):
    """Section détaillant l'Occupancy Rate par corps de métier. Retourne une liste
    d'éléments platypus (peut être vide si aucune donnée n'est disponible)."""
    elements = [Paragraph("Occupancy Rate par corps de métier" + (f" — Ligne {ligne}" if ligne else ""), h2_style)]

    occ = kpis_officiels.get("occupancy_rate")
    par_metier = occ.get("par_metier") if occ else None

    if not par_metier:
        msg = (
            f"Effectifs non configurés pour la ligne {ligne}." if ligne
            else "Aucune ligne sélectionnée lors de la génération du rapport."
        )
        elements.append(Paragraph(msg + " Voir la page /effectifs.", body_style))
        return elements

    data = [["Corps de métier", "Occupancy Rate"]]
    for craft, val in par_metier.items():
        data.append([craft, f"{val}%" if val is not None else "N/A"])

    table = Table(data, colWidths=[10 * cm, 6 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]))
    elements.append(table)
    return elements


def _equipements_semaine_section(interventions_correctives, nb_jours, date_debut=None, date_fin=None):
    """Section MTTR / MTBF / Disponibilité, uniquement pour les équipements
    ayant eu au moins une intervention corrective durant la semaine.
    Priorité à la saisie manuelle datée si elle existe pour la période,
    sinon estimation automatique (colonne 'Source')."""
    elements = [Paragraph("MTTR / MTBF / Disponibilité — équipements en intervention cette semaine", h2_style)]
    elements.append(Paragraph(
        "Priorité à vos saisies manuelles (page /equipements) si une saisie datée existe pour la "
        "période du rapport. Sinon, calcul approché basé sur les interventions correctives "
        "(les heures réelles d'intervention servent de proxy au temps d'arrêt). "
        "Ne couvre que les équipements ayant eu une intervention corrective sur la période.",
        muted_style
    ))
    elements.append(Spacer(1, 6))

    resultats = calculer_kpi_equipements_semaine(interventions_correctives, nb_jours, date_debut, date_fin)

    if not resultats:
        elements.append(Paragraph("Aucune intervention corrective sur la période.", body_style))
        return elements

    data = [["Tag équipement", "Nb pannes", "MTTR (h)", "MTBF (h)", "Disponibilité", "Source"]]
    for r in resultats:
        data.append([
            r["tag"] or "-",
            str(r["nb_pannes"]),
            f"{r['mttr']}" if r["mttr"] is not None else "N/A",
            f"{r['mtbf']}" if r["mtbf"] is not None else "N/A",
            f"{r['disponibilite']}%" if r["disponibilite"] is not None else "N/A",
            r.get("source", "-"),
        ])

    table = Table(data, colWidths=[5 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 2.4 * cm, 3.2 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(table)
    return elements


def _interventions_table(title, interventions, max_rows=10):
    elements = [Paragraph(title, h2_style)]
    rows = interventions[:max_rows]
    data = [["Date", "Tag équipement", "Description", "Statut"]]
    if not rows:
        data.append(["-", "-", "Aucune intervention sur la période", "-"])
    else:
        for item in rows:
            d = item.get("date")
            data.append([
                d.strftime("%d/%m/%Y") if d else "-",
                item.get("tag_equipement") or "-",
                (item.get("description") or "-")[:70],
                item.get("statut") or "-",
            ])

    table = Table(data, colWidths=[2.2 * cm, 3.5 * cm, 8.8 * cm, 2 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(table)
    return elements


def generate_weekly_report(week_data, kpis_officiels, output_path, ligne=None):
    """Construit le rapport PDF hebdomadaire et l'enregistre à output_path."""
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm
    )
    story = []

    debut = week_data["periode"]["debut"]
    fin = week_data["periode"]["fin"]
    nb_jours = week_data["periode"]["nb_jours"]
    periode_str = f"{debut.strftime('%d/%m/%Y')} — {fin.strftime('%d/%m/%Y')}" if debut and fin else ""

    story.append(Paragraph("Rapport Hebdomadaire d'Exécution Maintenance", title_style))
    story.append(Paragraph(periode_str + (f" — Ligne {ligne}" if ligne else ""), muted_style))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Indicateurs de la semaine", h2_style))
    story.append(_kpi_table(week_data["kpis"], kpis_officiels))
    story.append(Spacer(1, 16))

    with tempfile.TemporaryDirectory() as tmpdir:
        if week_data["heures_semaine"]:
            chart_path = _chart_heures_par_corps(week_data["heures_semaine"], tmpdir)
            story.append(Paragraph("Charge de travail par corps de métier", h2_style))
            story.append(Image(chart_path, width=15 * cm, height=7.4 * cm))

        story.append(Spacer(1, 16))
        story.extend(_occupancy_detail_section(kpis_officiels, ligne))

        story.append(PageBreak())
        story.extend(_equipements_semaine_section(week_data["interventions_correctives"], nb_jours, debut, fin))

        story.append(PageBreak())
        story.extend(_interventions_table("Interventions urgentes", week_data["interventions_urgentes"]))
        story.append(Spacer(1, 16))
        story.extend(_interventions_table("Interventions correctives", week_data["interventions_correctives"]))

        story.append(PageBreak())
        k = week_data["kpis"]
        story.append(Paragraph("Synthèse de la semaine", h2_style))
        taux = k["taux_execution"]
        appreciation = (
            "Données insuffisantes pour évaluer la performance." if taux is None else
            "Excellent taux d'exécution, performance conforme aux objectifs." if taux >= 90 else
            "Taux d'exécution correct, quelques écarts à surveiller." if taux >= 75 else
            "Taux d'exécution en dessous des objectifs, actions correctives recommandées."
        )
        bullets = [
            f"{k['total_executes']} OT exécutés sur {k['total_planifie']} planifiés"
            + (f" ({taux}%)" if taux is not None else ""),
            f"{k['total_non_planifie']} interventions non planifiées traitées",
            f"{k['total_heures_reel']:.1f} h réelles contre {k['total_heures_estime']:.1f} h estimées",
            appreciation,
        ]
        for b in bullets:
            story.append(Paragraph(f"• {b}", body_style))
            story.append(Spacer(1, 4))

        doc.build(story)

    return output_path