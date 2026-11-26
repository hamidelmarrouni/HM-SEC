// Docker defaults to same-origin requests, so LAN, VPN and localhost all work.
function resolveBaseUrl(value: string | undefined): string {
  return !value || value === "auto" ? window.location.origin : value.replace(/\/+$/, "");
}

export const BACKEND_BASE_URL = resolveBaseUrl(import.meta.env.VITE_BACKEND_BASE_URL);
export const FRONTEND_BASE_URL = resolveBaseUrl(import.meta.env.VITE_FRONTEND_BASE_URL);
