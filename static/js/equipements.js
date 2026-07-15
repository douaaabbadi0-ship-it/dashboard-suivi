const jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];
const CAUSES_PANNE = ["Mécanique", "Électrique", "Régulation", "Process"];
const tbody = document.querySelector("#tableauJours tbody");

jours.forEach((jour, index) => {
  const tr = document.createElement("tr");

  const optionsHtml = ['<option value="">--</option>']
    .concat(CAUSES_PANNE.map(c => `<option value="${c}">${c}</option>`))
    .join("");

  tr.innerHTML = `
    <td>${jour}</td>
    <td><input type="number" min="0" class="nbPannes" data-index="${index}" value="0"></td>
    <td><input type="number" min="0" step="0.5" class="heuresArret" data-index="${index}" value="0"></td>
    <td>
      <select class="causePanne" data-index="${index}">
        ${optionsHtml}
      </select>
    </td>
    <td><input type="text" class="commentaire" data-index="${index}" placeholder="Commentaire (optionnel)"></td>
  `;
  tbody.appendChild(tr);
});

document.getElementById("btnCalculer").addEventListener("click", async () => {
  const tag = document.getElementById("selectEquipement").value;
  if (!tag) {
    alert("Merci de sélectionner un équipement.");
    return;
  }

  const date = document.getElementById("dateSaisie").value;
  if (!date) {
    alert("Merci de renseigner la date de la saisie.");
    return;
  }

  const nbPannesInputs = document.querySelectorAll(".nbPannes");
  const heuresArretInputs = document.querySelectorAll(".heuresArret");
  const causePanneInputs = document.querySelectorAll(".causePanne");
  const commentaireInputs = document.querySelectorAll(".commentaire");

  const joursData = jours.map((jour, i) => ({
    date: jour,
    nb_pannes: parseFloat(nbPannesInputs[i].value) || 0,
    heures_arret: parseFloat(heuresArretInputs[i].value) || 0,
    cause: causePanneInputs[i].value || null,
    commentaire: commentaireInputs[i].value.trim() || null,
  }));

  const response = await fetch("/api/kpi-equipement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag, date, jours: joursData }),
  });

  const resultat = await response.json();

  document.getElementById("valMTTR").textContent = resultat.mttr + " h";
  document.getElementById("valMTBF").textContent = resultat.mtbf + " h";
  document.getElementById("valDispo").textContent = resultat.disponibilite + " %";
  document.getElementById("resultats").style.display = "flex";
});

document.getElementById("newZone").addEventListener("change", (e) => {
  const autreInput = document.getElementById("newZoneAutre");
  autreInput.style.display = e.target.value === "__autre__" ? "inline-block" : "none";
});

document.getElementById("btnAjouterEquipement").addEventListener("click", async () => {
  const tag = document.getElementById("newTag").value.trim();
  const categorie = document.getElementById("newCategorie").value.trim();
  let zone = document.getElementById("newZone").value;
  if (zone === "__autre__") {
    zone = document.getElementById("newZoneAutre").value.trim();
  }

  if (!tag || !categorie || !zone) {
    alert("Merci de remplir tous les champs.");
    return;
  }

  await fetch("/api/equipements", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag, categorie, zone }),
  });

  location.reload();
});