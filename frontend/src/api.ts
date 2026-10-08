export const API = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export type Sessao = { id: number; filme_id: number; data: string; hora: string; preco: number };
export type Filme = {
  id: number;
  titulo: string;
  ano: number | null;
  duracao_min: number | null;
  sinopse: string;
  imdb: string;
  letterboxd: string;
  critica: string;
  poster_url: string | null;
  thumb_url: string | null;
  sessoes: Sessao[];
};
export type Assentos = { vendidos: string[]; reservados: string[]; meus: string[] };

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = localStorage.getItem("adminToken");
  if (token && path.startsWith("/admin")) headers.set("X-Admin-Token", token);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  const r = await fetch(API + path, { ...init, headers });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = body.detail;
    const msg = Array.isArray(d) ? d.map((e: { msg: string }) => e.msg).join("; ") : d;
    throw Object.assign(new Error(msg || `Erro ${r.status}`), { status: r.status });
  }
  return body as T;
}

// Um id por aba (sessionStorage), para duas abas disputarem o mesmo assento na demo.
export const clientId =
  sessionStorage.getItem("clientId") ??
  (() => {
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    sessionStorage.setItem("clientId", id);
    return id;
  })();

export const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const duracao = (min: number | null) => (min ? `${Math.floor(min / 60)}h ${min % 60}min` : "");

export const erroMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));
