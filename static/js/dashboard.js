function pct(v) { return v === null || v === undefined ? '<span class="value unavailable">Non disponible</span>' : `${v}%`; }

function renderDashboard(data) {
    const k = data.kpis;
    const ko = data.kpis_officiels;
    const dashboardEl = document.getElementById("dashboard");
    const downloadBtn = document.getElementById("downloadBtn");

    let wrenchRows = "";
    for (const [craft, val] of Object.entries(ko.wrench_time_par_metier || {})) {
        wrenchRows += `<tr><td>${craft}</td><td>${val !== null ? val + "%" : "N/A"}</td></tr>`;
    }

    const occupancyGlobal = (ko.occupancy_rate && ko.occupancy_rate.global !== null && ko.occupancy_rate.global !== undefined)
        ? ko.occupancy_rate.global
        : null;

    let occupancyRows = "";
    if (ko.occupancy_rate && ko.occupancy_rate.par_metier) {
        for (const [craft, val] of Object.entries(ko.occupancy_rate.par_metier)) {
            occupancyRows += `<tr><td>${craft}</td><td>${val !== null ? val + "%" : "N/A"}</td></tr>`;
        }
    }

    dashboardEl.innerHTML = `
        <h2>Dashboard KPIs — ${data.periode.debut || ""} au ${data.periode.fin || ""}${data.ligne ? ` — Ligne ${data.ligne}` : ""}</h2>
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="value">${k.taux_execution !== null ? k.taux_execution + "%" : "N/A"}</div>
                <div class="label">Schedule Compliance</div>
            </div>
            <div class="kpi-card">
                <div class="value">${k.efficacite_temps !== null ? k.efficacite_temps + "%" : "N/A"}</div>
                <div class="label">MH réalisé / planifié</div>
            </div>
            <div class="kpi-card">
                <div class="value">${k.total_planifie}</div>
                <div class="label">OT planifiés</div>
            </div>
            <div class="kpi-card">
                <div class="value">${k.total_non_planifie}</div>
                <div class="label">OT non planifiés</div>
            </div>
            <div class="kpi-card">
                <div class="value">${ko.mttr_approx_heures !== null ? ko.mttr_approx_heures + " h" : "N/A"}</div>
                <div class="label">MTTR approché</div>
            </div>
            <div class="kpi-card">
                <div class="value unavailable">Non disponible</div>
                <div class="label">Rate of Rework</div>
            </div>
            <div class="kpi-card">
                <div class="value unavailable">Non disponible</div>
                <div class="label">WOs in Backlog</div>
            </div>
            <div class="kpi-card">
                ${occupancyGlobal !== null
                    ? `<div class="value">${occupancyGlobal}%</div>`
                    : `<div class="value unavailable">Non disponible</div>`}
                <div class="label">Occupancy rate</div>
            </div>
        </div>
        <h2>Direct Work Activity (wrench time) par corps de métier</h2>
        <table class="kpi-table">
            <thead><tr><th>Corps de métier</th><th>Réel / Estimé</th></tr></thead>
            <tbody>${wrenchRows || "<tr><td colspan='2'>Aucune donnée</td></tr>"}</tbody>
        </table>
        <h2>Occupancy Rate par corps de métier${data.ligne ? ` — Ligne ${data.ligne}` : ""}</h2>
        ${occupancyRows
            ? `<table class="kpi-table">
                <thead><tr><th>Corps de métier</th><th>Occupancy Rate</th></tr></thead>
                <tbody>${occupancyRows}</tbody>
            </table>`
            : `<p>${data.ligne
                ? `Effectifs non configurés pour la ligne ${data.ligne}. <a href="/effectifs">Renseigner les effectifs →</a>`
                : `Aucune ligne sélectionnée lors de la génération du rapport. <a href="/effectifs">Configurer les effectifs →</a>`}</p>`
        }
    `;
    dashboardEl.classList.remove("hidden");

    if (data.download_url) {
        downloadBtn.href = data.download_url;
        downloadBtn.classList.remove("hidden");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (window.resultatsInitiaux) {
        renderDashboard(window.resultatsInitiaux);

        const statusEl = document.getElementById("status");
        if (statusEl && window.resultatsInitiaux.nb_fichiers_traites !== undefined) {
            statusEl.className = "status success";
            statusEl.textContent = `${window.resultatsInitiaux.nb_fichiers_traites} fichier(s) analysé(s) avec succès.`;
        }
    }
});