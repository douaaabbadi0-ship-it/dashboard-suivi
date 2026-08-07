# -*- coding: utf-8 -*-
"""
reconciliation.py
Rapproche le Plan de Charge SAP (pdc_parser) avec les OTs realises
extraits des rapports journaliers (parser.aggregate_week), et calcule
les KPIs de man-hours / efficacite demandes.
"""

from pdc_parser import filter_semaine, index_by_ordre

# TODO (a confirmer avec l'ingenieur) : heures dues par jour.
# Le code existant (parser.py) utilise 8.8h/jour (TEMPS_JOURNALIER_MAROC)
# pour l'Occupancy Rate. La nouvelle demande specifie explicitement
# "8h a 17h avec 1h de pause" = 8h/jour. On garde ce chiffre separe
# pour ne pas casser les calculs existants, en attendant de savoir si
# les deux doivent coexister ou si l'un doit remplacer l'autre.
HEURES_DUES_PAR_JOUR = 8.0


def _numero_str(value):
    """Normalise un numero d'OT (venant des rapports journaliers) en string comparable a 'ordre'."""
    if value is None:
        return None
    s = str(value).strip()
    # Retire un ".0" residuel si le numero a ete lu comme float par openpyxl
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _est_realise(item):
    """
    Determine si une ligne d'OT (issue d'un rapport journalier) est consideree
    comme realisee.

    TODO (a confirmer) : on se base sur le flag statut (colonne L, "Y..."/"N...").
    Pour les OTs de la section "non_planifie" qui n'ont souvent pas de flag
    explicite, on les considere realises par defaut des lors qu'ils figurent
    dans le rapport journalier (puisqu'un superviseur ne rapporte que le
    travail effectivement fait sur le terrain).
    """
    statut = item.get("statut")
    if statut:
        return statut.strip().lower().startswith("y")
    return True


def reconcilier_semaine(week_data, pdc_rows):
    """
    Croise les OTs planifies dans le PDC SAP (filtres sur la semaine du
    rapport) avec les OTs realises extraits des rapports journaliers.

    Parametres :
        week_data : sortie de parser.aggregate_week()
        pdc_rows  : sortie de pdc_parser.parse_pdc() (liste complete, non filtree)

    Retourne un dict avec :
        - "planifie_realise"     : liste d'OTs (planifies SAP + vus realises terrain)
        - "planifie_non_realise" : liste d'OTs (planifies SAP + jamais vus realises)
        - "non_planifie_realise" : liste d'OTs (realises terrain + absents du PDC semaine)
        - "camembert"            : donnees pretes pour le graphe camembert
        - "barres"               : donnees pretes pour le graphe en batons
        - "man_hours"            : courbe journaliere heures reelles vs heures dues
    """
    date_debut = week_data["periode"]["debut"]
    date_fin = week_data["periode"]["fin"]

    pdc_semaine = filter_semaine(pdc_rows, date_debut, date_fin)
    pdc_index = index_by_ordre(pdc_semaine)
    ordres_planifies = set(pdc_index.keys())

    # Rassemble tous les OTs realises de la semaine (planifie + non_planifie),
    # tous rapports journaliers confondus.
    realises_par_numero = {}
    for rapport in week_data["rapports_journaliers"]:
        for section in (rapport["planifie"], rapport["non_planifie"]):
            for item in section:
                numero = _numero_str(item.get("numero"))
                if numero is None:
                    continue
                if _est_realise(item):
                    # On garde la premiere occurrence rencontree (au cas ou
                    # un meme OT apparaitrait sur plusieurs jours)
                    realises_par_numero.setdefault(numero, item)

    ordres_realises = set(realises_par_numero.keys())

    numeros_planifie_realise = ordres_planifies & ordres_realises
    numeros_planifie_non_realise = ordres_planifies - ordres_realises
    numeros_non_planifie_realise = ordres_realises - ordres_planifies

    planifie_realise = [
        {"ordre": n, "pdc": pdc_index[n][0], "realisation": realises_par_numero[n]}
        for n in numeros_planifie_realise
    ]
    planifie_non_realise = [
        {"ordre": n, "pdc": pdc_index[n][0]}
        for n in numeros_planifie_non_realise
    ]
    non_planifie_realise = [
        {"ordre": n, "realisation": realises_par_numero[n]}
        for n in numeros_non_planifie_realise
    ]

    camembert = {
        "labels": ["OT planifies realises", "OT planifies non realises"],
        "valeurs": [len(planifie_realise), len(planifie_non_realise)],
    }

    barres = {
        "labels": ["Planifie realise", "Planifie non realise", "Non planifie realise"],
        "valeurs": [
            len(planifie_realise),
            len(planifie_non_realise),
            len(non_planifie_realise),
        ],
    }

    man_hours = _calculer_man_hours(week_data)

    return {
        "planifie_realise": planifie_realise,
        "planifie_non_realise": planifie_non_realise,
        "non_planifie_realise": non_planifie_realise,
        "camembert": camembert,
        "barres": barres,
        "man_hours": man_hours,
        "nb_ot_pdc_semaine": len(pdc_semaine),
    }


def _calculer_man_hours(week_data, effectif_total=None):
    """
    Construit la courbe journaliere : heures reelles travaillees vs heures
    dues, pour mesurer l'efficacite pendant la semaine.

    TODO (a confirmer) : effectif_total doit venir de effectifs_kpi.py
    (meme source que pour l'Occupancy Rate existant) afin de calculer les
    heures dues = effectif_total x HEURES_DUES_PAR_JOUR par jour rapporte.
    Sans effectif fourni, on retourne uniquement les heures reelles (les
    heures dues et le taux d'efficacite restent a None).
    """
    courbe = []
    for rapport in week_data["rapports_journaliers"]:
        d = rapport["meta"]["date"]
        heures_reel = rapport["kpis"]["total_heures_reel"]

        heures_dues = (
            round(effectif_total * HEURES_DUES_PAR_JOUR, 2)
            if effectif_total else None
        )
        efficacite = (
            round(100 * heures_reel / heures_dues, 1)
            if heures_dues else None
        )

        courbe.append({
            "date": d,
            "heures_reel": heures_reel,
            "heures_dues": heures_dues,
            "efficacite_pct": efficacite,
        })

    courbe.sort(key=lambda x: x["date"] or "")
    return courbe