// JS de la aplicación. Funciones utilitarias compartidas.

// Formatea bytes a humano.
function humanSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

// Color de clase según score de confianza (0..1).
function confidenceClass(score) {
  if (score == null) return "";
  if (score >= 0.8) return "conf-high";
  if (score >= 0.5) return "conf-medium";
  return "conf-low";
}

// Drag & drop básico para dropzones. Pasar el id del form input oculto.
function setupDropzone(zoneEl, inputEl, onFiles) {
  zoneEl.addEventListener("click", () => inputEl.click());
  zoneEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    zoneEl.classList.add("drag-over");
  });
  zoneEl.addEventListener("dragleave", () => zoneEl.classList.remove("drag-over"));
  zoneEl.addEventListener("drop", (e) => {
    e.preventDefault();
    zoneEl.classList.remove("drag-over");
    if (e.dataTransfer.files.length) {
      inputEl.files = e.dataTransfer.files;
      if (onFiles) onFiles(e.dataTransfer.files);
    }
  });
  inputEl.addEventListener("change", () => {
    if (inputEl.files.length && onFiles) onFiles(inputEl.files);
  });
}
