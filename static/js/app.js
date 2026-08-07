const dropzone = document.getElementById("dropzone");
const dropzoneText = document.getElementById("dropzoneText");
const fileInput = document.getElementById("fileInput");
const fileListEl = document.getElementById("fileList");
const generateBtn = document.getElementById("generateBtn");
const statusEl = document.getElementById("status");
const ligneSelect = document.getElementById("ligneSelect");

// --- Nouveau : PDC SAP (fichier unique, optionnel) ---
const pdcDropzone = document.getElementById("pdcDropzone");
const pdcDropzoneText = document.getElementById("pdcDropzoneText");
const pdcFileInput = document.getElementById("pdcFileInput");
const pdcFileListEl = document.getElementById("pdcFileList");

let selectedFiles = [];
let selectedPdcFile = null; // un seul fichier, contrairement a selectedFiles

// Ajoute des fichiers à la liste existante, en évitant les doublons (même nom + même taille)
function addFiles(newFiles) {
    newFiles.forEach(f => {
        const alreadyExists = selectedFiles.some(
            existing => existing.name === f.name && existing.size === f.size
        );
        if (!alreadyExists) {
            selectedFiles.push(f);
        }
    });
    renderFileList();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
}

function renderFileList() {
    fileListEl.innerHTML = "";
    selectedFiles.forEach((f, index) => {
        const li = document.createElement("li");
        li.className = "file-item";

        const nameSpan = document.createElement("span");
        nameSpan.className = "file-name";
        nameSpan.textContent = f.name;

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "file-remove";
        removeBtn.textContent = "✕";
        removeBtn.setAttribute("aria-label", `Supprimer ${f.name}`);
        removeBtn.addEventListener("click", (e) => {
            e.stopPropagation(); // évite de rouvrir le sélecteur de fichiers (dropzone)
            removeFile(index);
        });

        li.appendChild(nameSpan);
        li.appendChild(removeBtn);
        fileListEl.appendChild(li);
    });

    generateBtn.disabled = selectedFiles.length === 0;
    dropzoneText.textContent = selectedFiles.length
        ? `${selectedFiles.length} fichier(s) sélectionné(s)`
        : "Glissez vos rapports journaliers (.xlsx) ici, ou cliquez pour sélectionner";
}

// --- Nouveau : gestion du fichier PDC SAP (un seul fichier à la fois) ---
function setPdcFile(file) {
    selectedPdcFile = file || null;
    renderPdcFileList();
}

function removePdcFile() {
    selectedPdcFile = null;
    renderPdcFileList();
}

function renderPdcFileList() {
    pdcFileListEl.innerHTML = "";

    if (selectedPdcFile) {
        const li = document.createElement("li");
        li.className = "file-item";

        const nameSpan = document.createElement("span");
        nameSpan.className = "file-name";
        nameSpan.textContent = selectedPdcFile.name;

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "file-remove";
        removeBtn.textContent = "✕";
        removeBtn.setAttribute("aria-label", `Supprimer ${selectedPdcFile.name}`);
        removeBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            removePdcFile();
        });

        li.appendChild(nameSpan);
        li.appendChild(removeBtn);
        pdcFileListEl.appendChild(li);
    }

    pdcDropzoneText.textContent = selectedPdcFile
        ? selectedPdcFile.name
        : "Plan de Charge SAP (.xlsx) — optionnel, pour comparer planifié / réalisé";
}

dropzone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", (e) => {
    addFiles(Array.from(e.target.files));
    // Réinitialise l'input pour permettre de re-sélectionner le même fichier plus tard si besoin
    fileInput.value = "";
});

["dragenter", "dragover"].forEach(evt =>
    dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    })
);

["dragleave", "drop"].forEach(evt =>
    dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
    })
);

dropzone.addEventListener("drop", (e) => {
    const dropped = Array.from(e.dataTransfer.files).filter(f =>
        f.name.endsWith(".xlsx") || f.name.endsWith(".xlsm")
    );
    addFiles(dropped);
});

// --- Nouveau : dropzone PDC SAP (même logique, mais un seul fichier) ---
pdcDropzone.addEventListener("click", () => pdcFileInput.click());

pdcFileInput.addEventListener("change", (e) => {
    const files = Array.from(e.target.files);
    if (files.length) {
        setPdcFile(files[0]);
    }
    pdcFileInput.value = "";
});

["dragenter", "dragover"].forEach(evt =>
    pdcDropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        pdcDropzone.classList.add("dragover");
    })
);

["dragleave", "drop"].forEach(evt =>
    pdcDropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        pdcDropzone.classList.remove("dragover");
    })
);

pdcDropzone.addEventListener("drop", (e) => {
    const dropped = Array.from(e.dataTransfer.files).filter(f =>
        f.name.endsWith(".xlsx") || f.name.endsWith(".xlsm")
    );
    if (dropped.length) {
        setPdcFile(dropped[0]);
    }
});

generateBtn.addEventListener("click", async () => {
    if (!selectedFiles.length) return;

    generateBtn.disabled = true;
    statusEl.className = "status";
    statusEl.textContent = "Analyse en cours...";

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append("daily_reports", f));
    if (ligneSelect) {
        formData.append("ligne", ligneSelect.value);
    }
    // Nouveau : PDC SAP, optionnel — n'est ajouté au formulaire que s'il a été sélectionné
    if (selectedPdcFile) {
        formData.append("pdc_sap", selectedPdcFile);
    }

    try {
        const res = await fetch("/api/generate", { method: "POST", body: formData });
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || "Erreur inconnue");
        }

        statusEl.className = "status success";
        statusEl.textContent = "Analyse terminée. Redirection vers le dashboard...";

        if (data.redirect) {
            window.location.href = data.redirect;
        }
    } catch (err) {
        statusEl.className = "status error";
        statusEl.textContent = `Erreur : ${err.message}`;
        generateBtn.disabled = false;
    }
});