const ligneSelect = document.getElementById("ligneSelect");
const btnEnregistrer = document.getElementById("btnEnregistrer");
const statusEl = document.getElementById("statusEffectifs");

let effectifsData = window.EFFECTIFS_INITIAL || {};

function remplirTableau(ligne) {
    const valeurs = effectifsData[ligne] || {};
    document.querySelectorAll(".effectif-input").forEach(input => {
        const metier = input.dataset.metier;
        input.value = valeurs[metier] ?? 0;
    });
}

ligneSelect.addEventListener("change", () => {
    remplirTableau(ligneSelect.value);
    statusEl.className = "status";
    statusEl.textContent = "";
});

btnEnregistrer.addEventListener("click", async () => {
    const ligne = ligneSelect.value;
    const effectifs = {};
    document.querySelectorAll(".effectif-input").forEach(input => {
        effectifs[input.dataset.metier] = parseInt(input.value, 10) || 0;
    });

    btnEnregistrer.disabled = true;
    statusEl.className = "status";
    statusEl.textContent = "Enregistrement en cours...";

    try {
        const res = await fetch("/api/effectifs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ligne, effectifs })
        });
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || "Erreur inconnue");
        }

        effectifsData = data;
        statusEl.className = "status success";
        statusEl.textContent = `Effectifs enregistrés pour la ligne ${ligne}.`;
    } catch (err) {
        statusEl.className = "status error";
        statusEl.textContent = `Erreur : ${err.message}`;
    } finally {
        btnEnregistrer.disabled = false;
    }
});

// Initialisation avec la ligne sélectionnée par défaut
remplirTableau(ligneSelect.value);