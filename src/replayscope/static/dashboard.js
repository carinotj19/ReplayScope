/* Progressive enhancement for the local Flask dashboard. */
(() => {
  "use strict";

  function message(form, value, isError = false) {
    const target = form.querySelector("[data-form-status]");
    if (target) {
      target.textContent = value;
      target.classList.toggle("error-text", isError);
    }
  }

  async function decode(response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Request failed (" + response.status + ")");
    }
    return payload;
  }

  const createForm = document.querySelector("[data-create-experiment]");
  if (createForm) {
    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = createForm.querySelector('button[type="submit"]');
      const input = createForm.querySelector('[name="name"]');
      const description = createForm.querySelector('[name="description"]');
      if (!input.value.trim()) {
        message(createForm, "Please enter an experiment name.", true);
        input.focus();
        return;
      }
      button.disabled = true;
      message(createForm, "Creating experiment…");
      try {
        const response = await fetch("/api/v1/experiments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: input.value.trim(), description: description.value }),
        });
        const payload = await decode(response);
        window.location.assign("/experiments/" + encodeURIComponent(payload.id));
      } catch (error) {
        message(createForm, error.message || "Unable to create experiment.", true);
      } finally {
        button.disabled = false;
      }
    });
  }

  const uploadForm = document.querySelector("[data-upload-form]");
  if (uploadForm) {
    const fileInput = uploadForm.querySelector('input[type="file"]');
    const label = uploadForm.querySelector(".upload-drop strong");
    if (fileInput && label) {
      fileInput.addEventListener("change", () => {
        label.textContent = fileInput.files.length
          ? fileInput.files[0].name : "Choose a benchmark file";
      });
    }

    async function pollUpload(id) {
      for (let attempt = 0; attempt < 30; attempt++) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const response = await fetch("/api/v1/uploads/" + encodeURIComponent(id));
        const upload = await decode(response);
        if (upload.status === "ready") {
          message(uploadForm, "Processed " + upload.run_count + " runs. Reloading…");
          window.location.reload();
          return;
        }
        if (upload.status === "failed") {
          throw new Error(upload.error || "Dataset processing failed");
        }
        message(uploadForm, "Processing… current status: " + upload.status);
      }
      message(uploadForm, "Still processing. Refresh this page later to see the result.");
    }

    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!fileInput.files.length) {
        message(uploadForm, "Select a JSON or CSV file first.", true);
        return;
      }
      const button = uploadForm.querySelector('button[type="submit"]');
      const form = new FormData();
      form.set("file", fileInput.files[0]);
      form.set("experiment_id", uploadForm.dataset.experimentId);
      button.disabled = true;
      message(uploadForm, "Validating and uploading…");
      try {
        const response = await fetch("/api/v1/uploads", { method: "POST", body: form });
        const upload = await decode(response);
        if (upload.status === "ready") {
          message(uploadForm, "Imported " + upload.run_count + " runs. Reloading…");
          window.location.reload();
        } else if (upload.status === "failed") {
          throw new Error(upload.error || "Dataset processing failed");
        } else {
          await pollUpload(upload.id);
        }
      } catch (error) {
        message(uploadForm, error.message || "Import failed.", true);
      } finally {
        button.disabled = false;
      }
    });
  }
})();
