/**
 * Inloggning med Microsoft (Entra) – samma app-registrering som portalen och
 * Arkitekten. Inställningarna kommer från api:t (GET /auth/config), så webbens
 * avbild behöver inga egna. Efter inloggningen byts Entra-token mot
 * plattformens egna (POST /auth/entra); resten av webben märker ingen skillnad.
 *
 * Omdirigeringen kommer tillbaka till /login (den adressen ska stå som SPA-
 * omdirigering i app-registreringen), där svaret tas om hand.
 */
import { PublicClientApplication } from "@azure/msal-browser";
import client from "./client";
import type { TokenResponse } from "./auth";

export interface EntraConfig {
  tenant_id: string;
  client_id: string;
  scope: string;
}

export async function fetchEntraConfig(): Promise<EntraConfig | null> {
  const r = await client.get("/auth/config");
  return r.data?.entra ?? null;
}

let msal: Promise<PublicClientApplication> | null = null;

function getMsal(cfg: EntraConfig): Promise<PublicClientApplication> {
  if (!msal) {
    msal = (async () => {
      const instance = new PublicClientApplication({
        auth: {
          clientId: cfg.client_id,
          authority: `https://login.microsoftonline.com/${cfg.tenant_id}`,
          redirectUri: `${window.location.origin}/login`,
          postLogoutRedirectUri: `${window.location.origin}/login`,
        },
        cache: { cacheLocation: "sessionStorage" },
      });
      await instance.initialize();
      return instance;
    })();
  }
  return msal;
}

export async function startEntraLogin(cfg: EntraConfig): Promise<void> {
  const instance = await getMsal(cfg);
  await instance.loginRedirect({ scopes: [cfg.scope] });
}

/** Svaret efter omdirigeringen, utbytt mot plattformens tokens – eller null om det inte var någon. */
export async function completeEntraLogin(cfg: EntraConfig): Promise<TokenResponse | null> {
  const instance = await getMsal(cfg);
  const result = await instance.handleRedirectPromise();
  if (!result?.accessToken) return null;
  const r = await client.post("/auth/entra", { access_token: result.accessToken });
  return r.data as TokenResponse;
}
