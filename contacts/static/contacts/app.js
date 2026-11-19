document.querySelectorAll(".dismiss-notice").forEach((button) => {
  button.addEventListener("click", () => button.closest(".notice").remove());
});

const fileInput = document.getElementById("contact-file");
const dropZone = document.getElementById("drop-zone");
const selectedFilename = document.getElementById("selected-filename");

if (fileInput && dropZone && selectedFilename) {
  const updateFilename = () => {
    selectedFilename.textContent = fileInput.files.length
      ? fileInput.files[0].name
      : "Файл не выбран";
    dropZone.classList.toggle("has-file", fileInput.files.length > 0);
  };
  fileInput.addEventListener("change", updateFilename);
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drag-over");
    });
  });
  dropZone.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) {
      const transfer = new DataTransfer();
      transfer.items.add(event.dataTransfer.files[0]);
      fileInput.files = transfer.files;
      updateFilename();
    }
  });
}


const searchInput = document.getElementById("ajax-search");
const searchResults = document.getElementById("ajax-results");
const searchStatus = document.querySelector("[data-search-status]");
if (searchInput && searchResults && searchStatus) {
  let timer;
  let controller;
  searchInput.addEventListener("input", () => {
    clearTimeout(timer);
    controller?.abort();
    const query = searchInput.value.trim();
    if (!query) {
      searchResults.replaceChildren();
      searchStatus.textContent = "";
      return;
    }
    searchStatus.textContent = "Поиск…";
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const url = new URL(searchInput.dataset.searchUrl, window.location.origin);
        url.searchParams.set("q", query);
        const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal });
        if (!response.ok) throw new Error("search failed");
        const data = await response.json();
        searchResults.replaceChildren();
        for (const record of data.results) {
          const item = document.createElement("article");
          item.className = "ajax-result";
          const name = document.createElement("strong");
          name.textContent = record.name;
          const details = document.createElement("span");
          details.textContent = [record.email, record.phone, record.company, record.city, record.category].filter(Boolean).join(" · ");
          const edit = document.createElement("a");
          edit.href = record.edit_url;
          edit.className = "button button-secondary";
          edit.textContent = "Изменить";
          item.append(name, details, edit);
          searchResults.append(item);
        }
        searchStatus.textContent = data.results.length ? `Найдено: ${data.results.length}` : "Ничего не найдено";
      } catch (error) {
        if (error.name !== "AbortError") searchStatus.textContent = "Не удалось выполнить поиск.";
      }
    }, 180);
  });
}

const storageTarget = document.querySelector('[data-storage-target]');
const fileFormatField = document.querySelector(".file-format-field");
const storageTargetField = document.querySelector(".storage-target-field");
const updateFileFormatVisibility = () => {
  if (!storageTarget || !fileFormatField) return;
  const visible = storageTarget.value === "file";
  fileFormatField.hidden = !visible;
  const formatSelect = fileFormatField.querySelector("select");
  formatSelect.disabled = !visible;
  formatSelect.required = visible;
  if (storageTargetField) storageTargetField.hidden = false;
};
storageTarget?.addEventListener("change", updateFileFormatVisibility);
updateFileFormatVisibility();
