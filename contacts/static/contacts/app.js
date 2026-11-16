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
