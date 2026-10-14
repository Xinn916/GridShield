import { request } from "./client.js";

export function listCatalogAssets() {
  return request("/api/v1/catalog/assets", { timeout: 10000 });
}

export function getCatalogAsset(assetId) {
  return request(`/api/v1/catalog/assets/${encodeURIComponent(assetId)}`, { timeout: 10000 });
}

export function listOwnerCatalogAssets() {
  return request("/api/v1/catalog/assets/owner", { timeout: 10000 });
}
