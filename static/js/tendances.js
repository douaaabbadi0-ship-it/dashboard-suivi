let chart = null;

const LABELS = {
    taux_execution: "Schedule Compliance (%)",
    efficacite_temps: "MH réalisé / planifié (%)",
    mttr_approx_heures: "MTTR approché (h)",
    occupancy_rate_global: "Occupancy Rate (%)",
};

function extraireValeur(rapport, kpi) {
    const k = rapport.kpis || {};
    const ko = rapport.kpis_officiels || {};

    switch (kpi) {
        case "taux_execution":
            return k.taux_execution ?? null;
        case "efficacite_temps":
            return k.efficacite_temps ?? null;
        case "mttr_approx_heures":
            return ko.mttr_approx_heures ?? null;
        case "occupancy_rate_global":
            return (ko.occupancy_rate && ko.occupancy_rate.global !== undefined)
                ? ko.occupancy_rate.global
                : null;
        default:
            return null;
    }
}

async function chargerTendance() {
    const ligne = document.getElementById("ligneSelect").value;
    const kpi = document.getElementById("kpiSelect").value;
    const statusEl = document.getElementById("chartStatus");

    statusEl.textContent = "Chargement...";
    statusEl.className = "status";

    const res = await fetch(`/api/historique-kpi?ligne=${encodeURIComponent(ligne)}`);
    if (!res.ok) {
        statusEl.textContent = "Erreur lors du chargement de l'historique.";
        statusEl.className = "status error";
        return;
    }

    const rapports = await res.json();

    if (!rapports.length) {
        statusEl.textContent = `Aucun rapport enregistré pour la ligne ${ligne} pour le moment.`;
        renderChart([], [], kpi);
        return;
    }

    if (rapports.length < 2) {
        statusEl.textContent = "Historique insuffisant pour une tendance (2 semaines minimum) — un seul point affiché.";
    } else {
        statusEl.textContent = `${rapports.length} semaines chargées.`;
        statusEl.className = "status success";
    }

    const labels = rapports.map(r => r.periode_fin || r.periode_debut || "?");
    const valeurs = rapports.map(r => extraireValeur(r, kpi));

    renderChart(labels, valeurs, kpi);
}

function renderChart(labels, valeurs, kpi) {
    const ctx = document.getElementById("tendanceChart").getContext("2d");
    if (chart) chart.destroy();

    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: LABELS[kpi] || kpi,
                data: valeurs,
                borderColor: "#22d3ee",
                backgroundColor: "rgba(34, 211, 238, 0.15)",
                spanGaps: true,
                tension: 0.25,
                pointRadius: 4,
                fill: true,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: false } },
            plugins: { legend: { labels: { color: "#e5e7eb" } } },
        },
    });
}

document.addEventListener("DOMContentLoaded", () => {
    chargerTendance();
    document.getElementById("ligneSelect").addEventListener("change", chargerTendance);
    document.getElementById("kpiSelect").addEventListener("change", chargerTendance);
});