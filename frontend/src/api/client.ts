import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

const client = axios.create({ baseURL });

// Attach auth to every request: JWT token if logged in, or admin API key as fallback
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`;
  } else {
    // Fallback for MCP server / scripts
    const adminKey = localStorage.getItem("admin_api_key");
    if (adminKey) {
      config.headers["X-Api-Key"] = adminKey;
    }
  }
  return config;
});

// On 401, clear tokens and redirect to login
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && localStorage.getItem("access_token")) {
      // Token expired or invalid — don't redirect if on login/setup page
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/setup") {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        sessionStorage.removeItem("refresh_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default client;
