const JOURS_SEMAINE = ['Lu', 'Ma', 'Me', 'Je', 'Ve', 'Sa', 'Di'];
const NOMS_MOIS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

function toDate(str) {
    const [y, m, d] = str.split('-').map(Number);
    return new Date(y, m - 1, d);
}

function addDays(date, n) {
    const d = new Date(date);
    d.setDate(d.getDate() + n);
    return d;
}

function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() &&
           a.getMonth() === b.getMonth() &&
           a.getDate() === b.getDate();
}

// Détermine le statut d'une date : 'generee', 'manquant', ou null (hors période suivie)
function statutDuJour(date, semaines) {
    for (const s of semaines) {
        const debut = toDate(s.periode_debut);
        const fin = addDays(debut, 6);
        if (date >= debut && date <= fin) {
            return s.generee ? 'generee' : 'manquant';
        }
    }
    return null;
}

function construireCalendrier(annee, mois, semaines) {
    const moisDiv = document.createElement('div');
    moisDiv.className = 'calendar-month';

    const titre = document.createElement('h3');
    titre.textContent = `${NOMS_MOIS[mois]} ${annee}`;
    moisDiv.appendChild(titre);

    const grille = document.createElement('div');
    grille.className = 'calendar-grid';

    JOURS_SEMAINE.forEach(j => {
        const entete = document.createElement('div');
        entete.className = 'calendar-weekday';
        entete.textContent = j;
        grille.appendChild(entete);
    });

    const premierJour = new Date(annee, mois, 1);
    const dernierJour = new Date(annee, mois + 1, 0);

    // Décalage pour commencer la grille un lundi (getDay: 0=dimanche)
    let decalage = premierJour.getDay() - 1;
    if (decalage < 0) decalage = 6;

    for (let i = 0; i < decalage; i++) {
        const vide = document.createElement('div');
        vide.className = 'calendar-day calendar-day-vide';
        grille.appendChild(vide);
    }

    const aujourdHui = new Date();

    for (let jour = 1; jour <= dernierJour.getDate(); jour++) {
        const date = new Date(annee, mois, jour);
        const statut = statutDuJour(date, semaines);

        const caseJour = document.createElement('div');
        caseJour.className = 'calendar-day';
        if (statut === 'generee') caseJour.classList.add('day-generee');
        if (statut === 'manquant') caseJour.classList.add('day-manquant');
        if (sameDay(date, aujourdHui)) caseJour.classList.add('day-aujourdhui');

        caseJour.textContent = jour;
        grille.appendChild(caseJour);
    }

    moisDiv.appendChild(grille);
    return moisDiv;
}

async function chargerPlanning() {
    const ligne = document.getElementById('ligneSelectPlanning').value;
    const container = document.getElementById('calendarContainer');
    container.innerHTML = '<p class="status">Chargement...</p>';

    try {
        const response = await fetch(`/api/planning?ligne=${ligne}`);
        if (!response.ok) throw new Error('Erreur serveur');
        const semaines = await response.json();

        container.innerHTML = '';

        if (semaines.length === 0) {
            container.innerHTML = '<p class="status">Aucune donnée disponible pour cette ligne.</p>';
            return;
        }

        const dateDebut = toDate(semaines[0].periode_debut);
        const dateFin = new Date();

        let anneeCourante = dateDebut.getFullYear();
        let moisCourant = dateDebut.getMonth();

        while (anneeCourante < dateFin.getFullYear() ||
               (anneeCourante === dateFin.getFullYear() && moisCourant <= dateFin.getMonth())) {
            container.appendChild(construireCalendrier(anneeCourante, moisCourant, semaines));
            moisCourant++;
            if (moisCourant > 11) {
                moisCourant = 0;
                anneeCourante++;
            }
        }
    } catch (err) {
        container.innerHTML = '<p class="status error">Erreur lors du chargement du planning.</p>';
        console.error(err);
    }
}

document.getElementById('ligneSelectPlanning').addEventListener('change', chargerPlanning);
window.addEventListener('DOMContentLoaded', chargerPlanning);