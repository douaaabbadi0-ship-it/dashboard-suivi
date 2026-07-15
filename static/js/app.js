const dropzone = document.getElementById("dropzone");
const dropzoneText = document.getElementById("dropzoneText");
const fileInput = document.getElementById("fileInput");
const fileListEl = document.getElementById("fileList");
const generateBtn = document.getElementById("generateBtn");
const statusEl = document.getElementById("status");
const ligneSelect = document.getElementById("ligneSelect");

let selectedFiles = [];

function renderFileList() {
    fileListEl.innerHTML = "";
    selectedFiles.forEach(f => {
        const li = document.createElement("li");
        li.textContent = f.name;
        fileListEl.appendChild(li);
    });
    generateBtn.disabled = selectedFiles.length === 0;
    dropzoneText.textContent = selectedFiles.length
        ? `${selectedFiles.length} fichier(s) sélectionné(s)`
        : "Glissez vos rapports journaliers (.xlsx) ici, ou cliquez pour sélectionner";
}

dropzone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", (e) => {
    selectedFiles = Array.from(e.target.files);
    renderFileList();
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
    selectedFiles = Array.from(e.dataTransfer.files).filter(f =>
        f.name.endsWith(".xlsx") || f.name.endsWith(".xlsm")
    );
    renderFileList();
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