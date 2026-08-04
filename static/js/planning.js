async function chargerPlanning() {
    const ligne = document.getElementById('ligneSelectPlanning').value;
    const liste = document.getElementById('planningList');
    liste.innerHTML = '<li>Chargement...</li>';

    try {
        const response = await fetch(`/api/planning?ligne=${ligne}`);
        if (!response.ok) throw new Error('Erreur serveur');
        const semaines = await response.json();

        liste.innerHTML = '';

        if (semaines.length === 0) {
            liste.innerHTML = '<li>Aucune donnée disponible pour cette ligne.</li>';
            return;
        }

        semaines.forEach(s => {
            const li = document.createElement('li');
            li.className = s.generee ? 'planning-ok' : 'planning-manquant';
            li.innerHTML = `${s.generee ? '✅' : '❌'} Semaine du ${s.periode_debut}`;
            liste.appendChild(li);
        });
    } catch (err) {
        liste.innerHTML = '<li>Erreur lors du chargement du planning.</li>';
        console.error(err);
    }
}

document.getElementById('ligneSelectPlanning').addEventListener('change', chargerPlanning);
window.addEventListener('DOMContentLoaded', chargerPlanning);
