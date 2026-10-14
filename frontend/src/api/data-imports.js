import { request } from "./client.js";

export function getDataImportConfig() {
  return request("/api/v1/data-imports/config");
}

export function listMyDataImports() {
  return request("/api/v1/data-imports/mine", { timeout: 20000 });
}

export function getActiveDataVersion() {
  return request("/api/v1/data-imports/active", { timeout: 20000 });
}

export function uploadDataImport(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  return request("/api/v1/data-imports", {
    method: "POST",
    body: form,
    timeout: 180000,
  });
}

export function activateDataImport(importId) {
  return request(`/api/v1/data-imports/${encodeURIComponent(importId)}/activate`, {
    method: "POST",
    timeout: 30000,
  });
}

export function rollbackDataImport(targetVersion) {
  return request(`/api/v1/data-imports/${encodeURIComponent(targetVersion)}/rollback`, {
    method: "POST",
    body: { target_version: targetVersion },
    timeout: 30000,
  });
}
