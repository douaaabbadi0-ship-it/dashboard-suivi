# -*- coding: utf-8 -*-
"""
pdf_generator.py
Génère le rapport hebdomadaire au format PDF avec reportlab.

Version enrichie :
- Cartes KPI colorées en page de garde (code couleur vert/orange/rouge)
- Sommaire cliquable avec numéros de page réels (TableOfContents reportlab)
- Résumé exécutif en page 2 avec recommandations générées automatiquement
- Encart "équipements critiques" basé sur le Pareto (règle des 80%)
- Graphique en camembert : répartition préventif / correctif
- Graphique d'évolution quotidienne (heures réelles vs estimées par jour)
- Tableau des indicateurs avec couleur conditionnelle sur les valeurs
- Diagrammes de Pareto (équipement / cause de panne)
- Rapprochement PDC SAP / réalisé : camembert, graphe en bâtons, courbe man-hours
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
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)
from reportlab.platypus.tableofcontents import TableOfContents

from equipment_kpi import calculer_kpi_equipements_semaine

# ---------------------------------------------------------------------------
# Palette de couleurs
# ---------------------------------------------------------------------------
NAVY = colors.HexColor("#1E2761")
ICE_BLUE = colors.HexColor("#CADCFC")
GREY = colors.HexColor("#6B6B6B")
LIGHT_BG = colors.HexColor("#F4F6FB")

GREEN = colors.HexColor("#2E7D32")
GREEN_BG = colors.HexColor("#E6F4EA")
ORANGE = colors.HexColor("#B26A00")
ORANGE_BG = colors.HexColor("#FDF0DC")
RED = colors.HexColor("#B3261E")
RED_BG = colors.HexColor("#FBE9E7")
NEUTRAL_BG = colors.HexColor("#EDEDED")

CHART_PALETTE = ["#1E2761", "#4C6EF5", "#748FFC", "#CADCFC", "#B26A00", "#B3261E"]

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], textColor=NAVY, fontSize=22, spaceAfter=6)
cover_title_style = ParagraphStyle(
    "CoverTitle", parent=styles["Title"], textColor=NAVY, fontSize=26, leading=32, alignment=TA_CENTER
)
h2_style = ParagraphStyle("H2Custom", parent=styles["Heading2"], textColor=NAVY, spaceBefore=14, spaceAfter=8)
# Style dédié aux titres de section qui NE doivent PAS apparaître dans le sommaire
# (ex: les sous-titres de Pareto), afin de garder un sommaire lisible avec
# uniquement les grandes sections du rapport.
h2_no_toc_style = ParagraphStyle("H2NoToc", parent=h2_style)
body_style = ParagraphStyle("BodyCustom", parent=styles["Normal"], fontSize=10, leading=14)
muted_style = ParagraphStyle("Muted", parent=styles["Normal"], fontSize=9, textColor=GREY)

toc_title_style = ParagraphStyle("TocTitle", parent=styles["Heading1"], textColor=NAVY, spaceAfter=14)
toc_entry_style = ParagraphStyle("TocEntry", parent=styles["Normal"], fontSize=11, leading=18, textColor=NAVY)

kpi_card_value_style = ParagraphStyle(
    "KpiCardValue", parent=styles["Normal"], fontSize=20, leading=22, alignment=1
)
kpi_card_label_style = ParagraphStyle(
    "KpiCardLabel", parent=styles["Normal"], fontSize=8.5, leading=11, alignment=1, textColor=GREY
)

reco_style = ParagraphStyle("Reco", parent=styles["Normal"], fontSize=10, leading=15, leftIndent=8)

# Style dédié à la colonne "Tag équipement" des tableaux d'interventions :
# utilisé en Paragraph (et non en texte brut) pour permettre le retour à la
# ligne automatique sur les tags longs (ex: JF06-PE-107A-RECYCL-000P04),
# qui débordaient sinon sur la colonne "Description" voisine.
tag_cell_style = ParagraphStyle("TagCell", parent=body_style, fontSize=8, leading=10)


# ---------------------------------------------------------------------------
# Fonctions utilitaires de seuils / couleurs
# ---------------------------------------------------------------------------
def _status_colors(value, good=90, warn=75, higher_is_better=True):
    """Retourne (couleur_texte, couleur_fond) selon la valeur et les seuils.
    Si value est None, retourne des couleurs neutres (grises)."""
    if value is None:
        return GREY, NEUTRAL_BG

    if higher_is_better:
        if value >= good:
            return GREEN, GREEN_BG
        if value >= warn:
            return ORANGE, ORANGE_BG
        return RED, RED_BG
    else:
        if value <= good:
            return GREEN, GREEN_BG
        if value <= warn:
            return ORANGE, ORANGE_BG
        return RED, RED_BG


def _occupancy_status_colors(value):
    """L'Occupancy Rate est optimal proche de 85-100%. Trop bas = sous-utilisation,
    trop haut = risque de surcharge. On centre donc le code couleur autour de cette
    plage plutôt que d'appliquer un simple seuil croissant."""
    if value is None:
        return GREY, NEUTRAL_BG
    if 80 <= value <= 105:
        return GREEN, GREEN_BG
    if 65 <= value < 80 or 105 < value <= 115:
        return ORANGE, ORANGE_BG
    return RED, RED_BG


# ---------------------------------------------------------------------------
# Doc template avec sommaire cliquable (numéros de page réels)
# ---------------------------------------------------------------------------
class ReportDocTemplate(BaseDocTemplate):
    """
    BaseDocTemplate personnalisé pour générer un sommaire avec de vrais numéros
    de page. Chaque Paragraph utilisant le style 'H2Custom' est automatiquement
    enregistré comme entrée de sommaire (avec bookmark cliquable), en captant
    sa position via afterFlowable. Les titres utilisant 'H2NoToc' (sous-titres
    Pareto, etc.) sont volontairement exclus pour garder le sommaire concis.
    Nécessite doc.multiBuild(story) au lieu de doc.build(story).
    """

    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="normal", frames=[frame])])
        self._toc_counter = 0

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "H2Custom":
            text = flowable.getPlainText()
            self._toc_counter += 1
            key = f"toc-{self._toc_counter}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify("TOCEntry", (0, text, self.page))


def _build_toc():
    toc = TableOfContents()
    toc.levelStyles = [toc_entry_style]
    return toc


# ---------------------------------------------------------------------------
# Page de garde : cartes KPI
# ---------------------------------------------------------------------------
def _kpi_cards_section(kpis, kpis_officiels):
    """Construit une rangée de cartes KPI colorées façon 'dashboard', pour donner
    un aperçu visuel immédiat en première page."""
    taux = kpis["taux_execution"]
    efficacite = kpis["efficacite_temps"]
    mttr = kpis_officiels.get("mttr_approx_heures")
    occ = kpis_officiels.get("occupancy_rate")
    occ_global = occ.get("global") if occ else None

    cards_data = [
        ("Taux d'exécution", f"{taux}%" if taux is not None else "N/A", _status_colors(taux)),
        ("Efficacité temps", f"{efficacite}%" if efficacite is not None else "N/A", _status_colors(efficacite)),
        ("MTTR approché", f"{mttr} h" if mttr is not None else "N/A", (GREY, NEUTRAL_BG)),
        ("Occupancy rate", f"{occ_global}%" if occ_global is not None else "N/A", _occupancy_status_colors(occ_global)),
    ]

    card_width = 4 * cm
    card_height = 2.6 * cm

    row_values = []
    row_styles = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]

    for i, (label, value_str, (text_color, bg_color)) in enumerate(cards_data):
        # Le "#" devant le code couleur hexadecimal est requis par reportlab
        # dans les balises <font color="...">.
        value_p = Paragraph(f'<font color="#{text_color.hexval()[2:]}"><b>{value_str}</b></font>', kpi_card_value_style)
        label_p = Paragraph(label, kpi_card_label_style)
        cell_table = Table([[value_p], [label_p]], colWidths=[card_width])
        cell_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        row_values.append(cell_table)
        row_styles.append(("BACKGROUND", (i, 0), (i, 0), bg_color))
        row_styles.append(("BOX", (i, 0), (i, 0), 0.75, colors.HexColor("#DDDDDD")))

    table = Table([row_values], colWidths=[card_width] * len(cards_data), rowHeights=[card_height])
    table.setStyle(TableStyle(row_styles))
    return table


# ---------------------------------------------------------------------------
# Graphiques matplotlib
# ---------------------------------------------------------------------------
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


def _chart_repartition_types(nb_preventif, nb_correctif, nb_urgent, tmpdir):
    """Camembert : répartition des interventions par type (préventif / correctif / urgent).
    Retourne None si aucune donnée exploitable (évite un graphique vide ou trompeur)."""
    labels, values, chart_colors = [], [], []

    if nb_preventif:
        labels.append("Préventif")
        values.append(nb_preventif)
        chart_colors.append("#1E2761")
    if nb_correctif:
        labels.append("Correctif")
        values.append(nb_correctif)
        chart_colors.append("#4C6EF5")
    if nb_urgent:
        labels.append("Urgent")
        values.append(nb_urgent)
        chart_colors.append("#B3261E")

    if not values:
        return None

    fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=chart_colors, autopct="%1.0f%%",
        startangle=90, textprops={"fontsize": 9}
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(9)
    ax.axis("equal")
    fig.tight_layout()

    path = os.path.join(tmpdir, "chart_repartition.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _chart_evolution_quotidienne(rapports_journaliers, tmpdir):
    """Graphique en barres groupées : heures réelles vs estimées, jour par jour
    sur la semaine. Donne une vision temporelle absente du seul total agrégé."""
    rapports = [r for r in rapports_journaliers if r["meta"].get("date")]
    if not rapports:
        return None

    rapports = sorted(rapports, key=lambda r: r["meta"]["date"])
    jours = [r["meta"]["date"].strftime("%d/%m") for r in rapports]
    reels = [r["kpis"]["total_heures_reel"] for r in rapports]
    estimes = [r["kpis"]["total_heures_estime"] for r in rapports]

    fig, ax = plt.subplots(figsize=(6.5, 3.2), dpi=150)
    x = range(len(jours))
    w = 0.35
    ax.bar([i - w / 2 for i in x], estimes, width=w, label="Estimé", color="#CADCFC")
    ax.bar([i + w / 2 for i in x], reels, width=w, label="Réel", color="#1E2761")
    ax.set_xticks(list(x))
    ax.set_xticklabels(jours, fontsize=8)
    ax.set_ylabel("Heures", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = os.path.join(tmpdir, "chart_evolution.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _chart_pareto(items, tmpdir, filename, value_label="Heures d'arrêt"):
    """
    Diagramme de Pareto générique : barres décroissantes (valeur brute) +
    courbe de pourcentage cumulé, avec une ligne de repère à 80%.

    items : liste de tuples (label, valeur), pas forcément triée en entrée.
    Retourne None si `items` est vide (évite un graphique vide/trompeur).
    """
    if not items:
        return None

    items_sorted = sorted(items, key=lambda kv: kv[1], reverse=True)
    labels = [str(k) for k, _ in items_sorted]
    values = [v for _, v in items_sorted]
    total = sum(values)

    cum_pct = []
    running = 0.0
    for v in values:
        running += v
        cum_pct.append(100 * running / total if total else 0)

    fig, ax1 = plt.subplots(figsize=(6.5, 3.6), dpi=150)
    x = range(len(labels))

    ax1.bar(x, values, color="#1E2761")
    ax1.set_ylabel(value_label, fontsize=9)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels, fontsize=7.5, rotation=35, ha="right")
    ax1.spines["top"].set_visible(False)

    ax2 = ax1.twinx()
    ax2.plot(x, cum_pct, color="#B3261E", marker="o", markersize=3.5, linewidth=1.5)
    ax2.set_ylim(0, 110)
    ax2.set_ylabel("% cumulé", fontsize=9)
    ax2.axhline(80, color="#B26A00", linestyle="--", linewidth=1)
    ax2.text(len(labels) - 0.5, 82, "80%", color="#B26A00", fontsize=7.5, ha="right")

    fig.tight_layout()
    path = os.path.join(tmpdir, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _equipements_critiques_80pct(resultats):
    """
    Applique la règle des 80/20 sur le temps d'arrêt cumulé par équipement :
    trie les équipements par heures_arret décroissant, et retient ceux qui
    concentrent (ensemble) les 80% premiers du total. Retourne une liste
    triée [(tag, heures_arret, part_pct), ...]. Liste vide si aucune donnée.
    """
    items = [(r["tag"] or "-", r.get("heures_arret") or 0) for r in resultats if r.get("heures_arret")]
    if not items:
        return []

    items_sorted = sorted(items, key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items_sorted)
    if not total:
        return []

    critiques = []
    running = 0.0
    for tag, val in items_sorted:
        running += val
        critiques.append((tag, val, round(100 * val / total, 1)))
        if running / total >= 0.8:
            break
    return critiques


# ---------------------------------------------------------------------------
# NOUVEAU : Graphiques de rapprochement PDC SAP / réalisé
# ---------------------------------------------------------------------------
def _chart_reconciliation_camembert(camembert, tmpdir):
    """
    Camembert : OT planifiés (SAP) réalisés vs non réalisés.
    `camembert` = reconciliation_result["camembert"], format :
    {"labels": [...], "valeurs": [...]}
    Retourne None si aucune donnée exploitable.
    """
    if not camembert:
        return None

    labels = camembert.get("labels", [])
    values = camembert.get("valeurs", [])
    if not values or sum(values) == 0:
        return None

    # Vert pour "réalisé", rouge pour "non réalisé" (ordre attendu du camembert
    # produit par reconciliation.reconcilier_semaine : [realise, non_realise]).
    palette = ["#2E7D32", "#B3261E"] if len(values) == 2 else CHART_PALETTE[:len(values)]

    fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=palette, autopct="%1.0f%%",
        startangle=90, textprops={"fontsize": 9}
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(9)
    ax.axis("equal")
    fig.tight_layout()

    path = os.path.join(tmpdir, "chart_pdc_camembert.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _chart_reconciliation_barres(barres, tmpdir):
    """
    Graphe en bâtons : nombre d'OT par catégorie (planifié réalisé /
    planifié non réalisé / non planifié réalisé).
    `barres` = reconciliation_result["barres"], format :
    {"labels": [...], "valeurs": [...]}
    Retourne None si aucune donnée exploitable.
    """
    if not barres:
        return None

    labels = barres.get("labels", [])
    values = barres.get("valeurs", [])
    if not values or sum(values) == 0:
        return None

    bar_colors = CHART_PALETTE[:len(labels)]

    fig, ax = plt.subplots(figsize=(6.5, 3.4), dpi=150)
    x = range(len(labels))
    bars = ax.bar(x, values, color=bar_colors)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Nombre d'OT", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for rect, v in zip(bars, values):
        ax.text(rect.get_x() + rect.get_width() / 2, v, str(v), ha="center", va="bottom", fontsize=8.5)

    fig.tight_layout()
    path = os.path.join(tmpdir, "chart_pdc_barres.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _chart_man_hours(man_hours, tmpdir):
    """
    Courbe/barres journalières : heures réelles vs heures dues sur la
    semaine, avec le taux d'efficacité en courbe (axe secondaire) quand
    les heures dues sont disponibles (effectifs configurés).
    `man_hours` = reconciliation_result["man_hours"], liste de dicts
    {"date": date, "heures_reel": float, "heures_dues": float|None,
     "efficacite_pct": float|None, ...}
    Retourne None si aucune donnée exploitable.
    """
    if not man_hours:
        return None

    rows = [r for r in man_hours if r.get("date")]
    if not rows:
        return None

    rows = sorted(rows, key=lambda r: r["date"])
    jours = [r["date"].strftime("%d/%m") if hasattr(r["date"], "strftime") else str(r["date"]) for r in rows]
    reels = [r.get("heures_reel") or 0 for r in rows]
    dues = [r.get("heures_dues") for r in rows]
    has_dues = any(d is not None for d in dues)

    fig, ax1 = plt.subplots(figsize=(6.5, 3.4), dpi=150)
    x = range(len(jours))

    if has_dues:
        dues_plot = [d if d is not None else 0 for d in dues]
        w = 0.35
        ax1.bar([i - w / 2 for i in x], dues_plot, width=w, label="Heures dues", color="#CADCFC")
        ax1.bar([i + w / 2 for i in x], reels, width=w, label="Heures réelles", color="#1E2761")
    else:
        ax1.bar(x, reels, width=0.5, label="Heures réelles", color="#1E2761")

    ax1.set_xticks(list(x))
    ax1.set_xticklabels(jours, fontsize=8)
    ax1.set_ylabel("Heures", fontsize=9)
    ax1.legend(frameon=False, fontsize=8, loc="upper left")
    ax1.spines["top"].set_visible(False)

    if has_dues:
        effs = [r.get("efficacite_pct") for r in rows]
        xs_valid = [i for i, e in enumerate(effs) if e is not None]
        ys_valid = [e for e in effs if e is not None]
        if ys_valid:
            ax2 = ax1.twinx()
            ax2.plot(xs_valid, ys_valid, color="#B26A00", marker="o", markersize=4, linewidth=1.5)
            ax2.set_ylabel("Efficacité (%)", fontsize=9)
            ax2.axhline(100, color="#6B6B6B", linestyle="--", linewidth=0.8)

    fig.tight_layout()
    path = os.path.join(tmpdir, "chart_man_hours.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _reconciliation_section(reconciliation, tmpdir, ligne):
    """
    Section "Rapprochement Plan de Charge SAP / Réalisé" : camembert
    planifié réalisé/non réalisé, graphe en bâtons des 3 catégories d'OT,
    et courbe man-hours (heures réelles vs heures dues).

    Si `reconciliation` est None (aucun PDC SAP fourni lors de la
    génération du rapport), affiche un message explicatif au lieu de la
    section, plutôt que de la faire disparaître silencieusement.
    """
    elements = [Paragraph("Rapprochement Plan de Charge SAP / Réalisé", h2_style)]

    if not reconciliation:
        elements.append(Paragraph(
            "Aucun Plan de Charge SAP n'a été fourni pour cette période. Cette section "
            "nécessite l'upload du fichier PDC SAP en plus des rapports journaliers "
            "pour comparer les OT planifiés aux OT réellement exécutés.",
            body_style
        ))
        return elements

    nb_pdc = reconciliation.get("nb_ot_pdc_semaine")
    elements.append(Paragraph(
        f"{nb_pdc} OT planifiés dans le PDC SAP sur la période"
        + (f" — Ligne {ligne}" if ligne else "") + ".",
        muted_style
    ))
    elements.append(Spacer(1, 10))

    camembert_path = _chart_reconciliation_camembert(reconciliation.get("camembert"), tmpdir)
    if camembert_path:
        elements.append(Image(camembert_path, width=10 * cm, height=8 * cm))
        elements.append(Spacer(1, 14))

    barres_path = _chart_reconciliation_barres(reconciliation.get("barres"), tmpdir)
    if barres_path:
        elements.append(Paragraph("OT planifiés vs réalisés (détail)", h2_no_toc_style))
        elements.append(Image(barres_path, width=15 * cm, height=7.9 * cm))
        elements.append(Spacer(1, 16))

    man_hours_data = reconciliation.get("man_hours")
    man_hours_path = _chart_man_hours(man_hours_data, tmpdir)
    if man_hours_path:
        elements.append(Paragraph("Man-hours : heures travaillées vs heures dues", h2_no_toc_style))
        has_dues = any(r.get("heures_dues") is not None for r in (man_hours_data or []))
        if not has_dues:
            elements.append(Paragraph(
                "Effectifs non configurés pour cette ligne (page /effectifs) : seules les heures "
                "réelles sont affichées, sans comparaison aux heures dues.",
                muted_style
            ))
            elements.append(Spacer(1, 4))
        elements.append(Image(man_hours_path, width=15 * cm, height=7.9 * cm))

    return elements


# ---------------------------------------------------------------------------
# Tableaux
# ---------------------------------------------------------------------------
def _kpi_table(kpis, kpis_officiels):
    occ = kpis_officiels.get("occupancy_rate")
    occ_global = occ.get("global") if occ else None
    occ_str = f"{occ_global}%" if occ_global is not None else "Non disponible (ligne ou effectifs non configurés)"

    taux = kpis["taux_execution"]
    efficacite = kpis["efficacite_temps"]
    mttr = kpis_officiels.get("mttr_approx_heures")

    rows_config = [
        ("Taux d'exécution (Schedule Compliance)",
         f"{taux}%" if taux is not None else "N/A", _status_colors(taux)),
        ("Efficacité temps (MH réalisé / MH planifié)",
         f"{efficacite}%" if efficacite is not None else "N/A", _status_colors(efficacite)),
        ("OT planifiés", str(kpis["total_planifie"]), None),
        ("OT non planifiés", str(kpis["total_non_planifie"]), None),
        ("MTTR approché (correctifs)",
         f"{mttr} h" if mttr is not None else "N/A", None),
        ("Rate of Rework", "Non disponible (données absentes)", None),
        ("WOs in Backlog", "Non disponible (données absentes)", None),
        ("WOs with Non-Compliance", "Non disponible (données absentes)", None),
        ("Occupancy rate", occ_str, _occupancy_status_colors(occ_global)),
    ]

    data = [["Indicateur", "Valeur"]]
    for label, value, _ in rows_config:
        data.append([label, value])

    table = Table(data, colWidths=[10 * cm, 6 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]

    # Couleur conditionnelle sur la colonne "Valeur" pour les lignes concernées
    for i, (_, _, status) in enumerate(rows_config, start=1):
        if status is not None:
            text_color, bg_color = status
            style_cmds.append(("TEXTCOLOR", (1, i), (1, i), text_color))
            style_cmds.append(("BACKGROUND", (1, i), (1, i), bg_color))
            style_cmds.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

    table.setStyle(TableStyle(style_cmds))
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
    row_colors = [None]
    for craft, val in par_metier.items():
        data.append([craft, f"{val}%" if val is not None else "N/A"])
        row_colors.append(_occupancy_status_colors(val))

    table = Table(data, colWidths=[10 * cm, 6 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]
    for i, status in enumerate(row_colors):
        if status is not None:
            text_color, bg_color = status
            style_cmds.append(("TEXTCOLOR", (1, i), (1, i), text_color))
            style_cmds.append(("BACKGROUND", (1, i), (1, i), bg_color))
            style_cmds.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

    table.setStyle(TableStyle(style_cmds))
    elements.append(table)
    return elements


def _equipements_semaine_section(resultats, nb_jours, tmpdir):
    """Section MTTR / MTBF / Disponibilité, uniquement pour les équipements
    ayant eu au moins une intervention corrective durant la semaine.
    Inclut aussi les deux diagrammes de Pareto (équipement / cause de panne).

    `resultats` est déjà calculé en amont (une seule fois, dans
    generate_weekly_report) et réutilisé ici ET dans le résumé exécutif,
    pour éviter un second appel Supabase redondant.
    """
    elements = [Paragraph("MTTR / MTBF / Disponibilité — équipements en intervention cette semaine", h2_style)]
    elements.append(Paragraph(
        "Priorité à vos saisies manuelles (page /equipements) si une saisie datée existe pour la "
        "période du rapport. Sinon, calcul approché basé sur les interventions correctives "
        "(les heures réelles d'intervention servent de proxy au temps d'arrêt). "
        "Ne couvre que les équipements ayant eu une intervention corrective sur la période.",
        muted_style
    ))
    elements.append(Spacer(1, 6))

    if not resultats:
        elements.append(Paragraph("Aucune intervention corrective sur la période.", body_style))
        return elements

    data = [["Tag équipement", "Nb pannes", "MTTR (h)", "MTBF (h)", "Disponibilité", "Source"]]
    dispo_colors = [None]
    for r in resultats:
        data.append([
            r["tag"] or "-",
            str(r["nb_pannes"]),
            f"{r['mttr']}" if r["mttr"] is not None else "N/A",
            f"{r['mtbf']}" if r["mtbf"] is not None else "N/A",
            f"{r['disponibilite']}%" if r["disponibilite"] is not None else "N/A",
            r.get("source", "-"),
        ])
        dispo_colors.append(_status_colors(r["disponibilite"], good=95, warn=85))

    table = Table(data, colWidths=[5 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 2.4 * cm, 3.2 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, status in enumerate(dispo_colors):
        if status is not None:
            text_color, bg_color = status
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), text_color))
            style_cmds.append(("BACKGROUND", (4, i), (4, i), bg_color))
            style_cmds.append(("FONTNAME", (4, i), (4, i), "Helvetica-Bold"))

    table.setStyle(TableStyle(style_cmds))
    elements.append(table)
    elements.append(Spacer(1, 14))

    # ---- Encart équipements critiques (règle des 80%) ----
    critiques = _equipements_critiques_80pct(resultats)
    if critiques:
        elements.append(_critical_equipment_box(critiques))
        elements.append(Spacer(1, 14))

    # ---- Pareto n°1 : par équipement (temps d'arrêt cumulé) ----
    items_equip = [(r["tag"] or "-", r["heures_arret"]) for r in resultats if r.get("heures_arret")]
    pareto_equip_path = _chart_pareto(items_equip, tmpdir, "pareto_equipement.png", value_label="Heures d'arrêt")
    if pareto_equip_path:
        elements.append(Paragraph("Pareto — Temps d'arrêt cumulé par équipement", h2_no_toc_style))
        elements.append(Image(pareto_equip_path, width=15 * cm, height=8.3 * cm))
        elements.append(Spacer(1, 14))

    # ---- Pareto n°2 : par cause de panne ----
    # ATTENTION : la cause n'est renseignée que pour les équipements dont la
    # source est "saisie manuelle" (page /equipements). Les rapports
    # journaliers Excel n'ont pas de colonne "cause de panne", donc les
    # équipements en source "estimé" ne contribuent pas à ce Pareto. Le
    # résultat est donc partiel et un avertissement est affiché en
    # conséquence, pour éviter une fausse impression d'exhaustivité.
    causes_totals = {}
    nb_avec_cause = 0
    for r in resultats:
        pc = r.get("pannes_par_cause")
        if pc:
            nb_avec_cause += 1
            for cause, nb in pc.items():
                causes_totals[cause] = causes_totals.get(cause, 0) + nb

    items_causes = list(causes_totals.items())
    pareto_cause_path = _chart_pareto(items_causes, tmpdir, "pareto_cause.png", value_label="Nb de pannes")

    if pareto_cause_path:
        elements.append(Paragraph("Pareto — Pannes par cause", h2_no_toc_style))
        nb_total = len(resultats)
        elements.append(Paragraph(
            f"Basé uniquement sur les équipements avec saisie manuelle datée ({nb_avec_cause} sur "
            f"{nb_total} équipements concernés cette semaine). Les rapports journaliers Excel ne "
            "contiennent pas de champ \"cause de panne\" : les équipements en source \"estimé\" "
            "n'apparaissent pas ici. Ce Pareto est donc partiel, pas une vue exhaustive de la semaine.",
            muted_style
        ))
        elements.append(Spacer(1, 6))
        elements.append(Image(pareto_cause_path, width=15 * cm, height=8.3 * cm))

    return elements


def _critical_equipment_box(critiques):
    """
    Encart visuel mettant en avant les équipements qui concentrent 80% du
    temps d'arrêt cumulé (règle de Pareto). Réutilisé dans le résumé exécutif
    ET dans la section MTTR.
    """
    header = Paragraph(
        '<font color="#B3261E"><b>⚠ Équipements critiques à surveiller</b></font> '
        '<font color="#6B6B6B" size="8">(concentrent 80% du temps d\'arrêt cumulé de la semaine)</font>',
        ParagraphStyle("CritHeader", parent=body_style, fontSize=10.5)
    )

    rows = [[header, ""]]
    data = [["Équipement", "Part du temps d'arrêt"]]
    for tag, heures, pct in critiques:
        data.append([tag, f"{pct}% ({heures} h)"])

    inner_table = Table(data, colWidths=[10 * cm, 6 * cm])
    inner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8D7D3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), RED),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, RED_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E8B4AE")),
    ]))

    outer = Table([[header], [inner_table]], colWidths=[16 * cm])
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, RED),
        ("BACKGROUND", (0, 0), (0, 0), RED_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return outer


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
                Paragraph(item.get("tag_equipement") or "-", tag_cell_style),
                (item.get("description") or "-")[:70],
                item.get("statut") or "-",
            ])

    table = Table(data, colWidths=[2.2 * cm, 4.3 * cm, 8 * cm, 2 * cm])
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


# ---------------------------------------------------------------------------
# Résumé exécutif
# ---------------------------------------------------------------------------
def _generer_recommandations(k, kpis_officiels, critiques):
    """
    Génère 2 à 5 recommandations textuelles selon des seuils métier, à partir
    des mêmes KPI que le reste du rapport. Purement basé sur des règles
    simples (pas d'IA/LLM), donc déterministe et explicable.
    """
    recos = []
    taux = k["taux_execution"]
    efficacite = k["efficacite_temps"]
    occ = kpis_officiels.get("occupancy_rate")
    occ_global = occ.get("global") if occ else None
    mttr = kpis_officiels.get("mttr_approx_heures")

    if taux is not None:
        if taux >= 95:
            recos.append("Taux d'exécution excellent : maintenir le rythme de planification actuel.")
        elif taux < 75:
            recos.append("Taux d'exécution sous l'objectif : revoir la charge planifiée ou les causes de non-exécution.")

    if efficacite is not None:
        if efficacite < 50:
            recos.append(
                "Écart important entre heures estimées et heures réelles : les temps standards utilisés pour "
                "planifier semblent surestimés par rapport à la réalité terrain — à recalibrer."
            )
        elif efficacite > 130:
            recos.append(
                "Heures réelles nettement supérieures aux heures estimées : risque de sous-planification "
                "de la charge ou de dérive sur les interventions."
            )

    if occ_global is not None:
        if occ_global < 65:
            recos.append(
                f"Occupancy rate faible ({occ_global}%) : effectifs potentiellement sous-utilisés sur la "
                "période, ou activité réelle inférieure à la capacité théorique disponible."
            )
        elif occ_global > 115:
            recos.append(
                f"Occupancy rate élevé ({occ_global}%) : risque de surcharge des équipes, à surveiller."
            )

    if critiques:
        tags = ", ".join(tag for tag, _, _ in critiques[:3])
        recos.append(
            f"{len(critiques)} équipement(s) concentrent 80% du temps d'arrêt de la semaine "
            f"(dont {tags}) : prioriser leur inspection préventive."
        )

    if mttr is not None and mttr > 4:
        recos.append(f"MTTR approché élevé ({mttr} h) : investiguer les délais d'intervention corrective.")

    if not recos:
        recos.append("Aucun signal critique détecté sur la période : indicateurs dans les plages attendues.")

    return recos


def _executive_summary_section(week_data, kpis_officiels, resultats, ligne):
    k = week_data["kpis"]
    debut = week_data["periode"]["debut"]
    fin = week_data["periode"]["fin"]
    periode_str = f"{debut.strftime('%d/%m/%Y')} — {fin.strftime('%d/%m/%Y')}" if debut and fin else ""

    elements = [Paragraph("Résumé exécutif", h2_style)]
    elements.append(Paragraph(
        f"Période : {periode_str}" + (f" — Ligne {ligne}" if ligne else ""), muted_style
    ))
    elements.append(Spacer(1, 10))
    elements.append(_kpi_cards_section(k, kpis_officiels))
    elements.append(Spacer(1, 18))

    elements.append(Paragraph("Recommandations", h2_no_toc_style))
    critiques = _equipements_critiques_80pct(resultats)
    recos = _generer_recommandations(k, kpis_officiels, critiques)
    for reco in recos:
        elements.append(Paragraph(f"• {reco}", reco_style))
        elements.append(Spacer(1, 3))

    if critiques:
        elements.append(Spacer(1, 12))
        elements.append(_critical_equipment_box(critiques))

    return elements


# ---------------------------------------------------------------------------
# Page de garde
# ---------------------------------------------------------------------------
def _page_de_garde(periode_str, ligne):
    elements = [Spacer(1, 5 * cm)]
    elements.append(Paragraph("Rapport Hebdomadaire", cover_title_style))
    elements.append(Paragraph("d'Exécution Maintenance", cover_title_style))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        periode_str + (f" — Ligne {ligne}" if ligne else ""),
        ParagraphStyle("CoverSub", parent=styles["Normal"], fontSize=13, alignment=TA_CENTER, textColor=GREY)
    ))
    elements.append(Spacer(1, 2 * cm))
    bar = Table([[""]], colWidths=[8 * cm], rowHeights=[0.15 * cm])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY)]))
    bar.hAlign = "CENTER"
    elements.append(bar)
    elements.append(PageBreak())

    elements.append(Paragraph("Sommaire", toc_title_style))
    elements.append(_build_toc())
    elements.append(PageBreak())
    return elements


# ---------------------------------------------------------------------------
# Génération du rapport
# ---------------------------------------------------------------------------
def generate_weekly_report(week_data, kpis_officiels, output_path, ligne=None, reconciliation=None):
    """
    Construit le rapport PDF hebdomadaire et l'enregistre à output_path.

    reconciliation : sortie optionnelle de reconciliation.reconcilier_semaine()
    (None si aucun PDC SAP n'a été fourni). Ajoute la section "Rapprochement
    Plan de Charge SAP / Réalisé" avec camembert, graphe en bâtons et courbe
    man-hours.
    """
    doc = ReportDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm
    )
    story = []

    debut = week_data["periode"]["debut"]
    fin = week_data["periode"]["fin"]
    nb_jours = week_data["periode"]["nb_jours"]
    periode_str = f"{debut.strftime('%d/%m/%Y')} — {fin.strftime('%d/%m/%Y')}" if debut and fin else ""

    k = week_data["kpis"]

    # Calculé UNE SEULE FOIS ici, puis réutilisé pour le résumé exécutif ET
    # la section MTTR/Pareto plus bas (évite un second appel Supabase).
    resultats_equipements = calculer_kpi_equipements_semaine(
        week_data["interventions_correctives"], nb_jours, debut, fin
    )

    # ---- Page de garde + sommaire ----
    story.extend(_page_de_garde(periode_str, ligne))

    # ---- Résumé exécutif ----
    story.extend(_executive_summary_section(week_data, kpis_officiels, resultats_equipements, ligne))
    story.append(PageBreak())

    story.append(Paragraph("Indicateurs de la semaine", h2_style))
    story.append(_kpi_table(k, kpis_officiels))
    story.append(Spacer(1, 16))

    with tempfile.TemporaryDirectory() as tmpdir:
        # ---- Graphique heures par corps de métier ----
        if week_data["heures_semaine"]:
            chart_path = _chart_heures_par_corps(week_data["heures_semaine"], tmpdir)
            story.append(Paragraph("Charge de travail par corps de métier", h2_style))
            story.append(Image(chart_path, width=15 * cm, height=7.4 * cm))

        story.append(PageBreak())

        # ---- Graphique évolution quotidienne ----
        evol_path = _chart_evolution_quotidienne(week_data.get("rapports_journaliers", []), tmpdir)
        if evol_path:
            story.append(Paragraph("Évolution quotidienne : heures réelles vs estimées", h2_style))
            story.append(Image(evol_path, width=15 * cm, height=7.4 * cm))
            story.append(Spacer(1, 16))

        # ---- Camembert répartition des interventions ----
        repart_path = _chart_repartition_types(
            k["total_preventif"], k["total_correctif"], len(week_data["interventions_urgentes"]), tmpdir
        )
        if repart_path:
            story.append(Paragraph("Répartition des interventions par type", h2_style))
            story.append(Image(repart_path, width=10 * cm, height=8 * cm))

        # ---- NOUVEAU : Rapprochement PDC SAP / réalisé ----
        story.append(PageBreak())
        story.extend(_reconciliation_section(reconciliation, tmpdir, ligne))

        story.append(PageBreak())
        story.extend(_occupancy_detail_section(kpis_officiels, ligne))

        story.append(PageBreak())
        story.extend(_equipements_semaine_section(resultats_equipements, nb_jours, tmpdir))

        story.append(PageBreak())
        story.extend(_interventions_table("Interventions urgentes", week_data["interventions_urgentes"]))
        story.append(Spacer(1, 16))
        story.extend(_interventions_table("Interventions correctives", week_data["interventions_correctives"]))

        story.append(PageBreak())
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

        # multiBuild (au lieu de build) est nécessaire pour que le sommaire
        # ait le temps de collecter les numéros de page réels sur une
        # première passe, puis les injecte sur la passe finale.
        doc.multiBuild(story)

    return output_path