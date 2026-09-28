/**
 * Um `next/navigation` de mentira que acompanha o `history`, como o Next faz
 * no navegador: o `useSearchParams` muda quando a tela troca a URL com
 * `replaceState`. Para usar num teste:
 *
 *     vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);
 *     irPara("/receitas?aba=ranking");
 */

import { useSyncExternalStore } from "react";
import { vi } from "vitest";

const ouvintes = new Set<() => void>();

function avisar() {
  for (const ouvinte of ouvintes) ouvinte();
}

function assinar(ouvinte: () => void) {
  ouvintes.add(ouvinte);
  return () => {
    ouvintes.delete(ouvinte);
  };
}

const trocaOriginal = window.history.replaceState.bind(window.history);

window.history.replaceState = (...args: Parameters<History["replaceState"]>) => {
  trocaOriginal(...args);
  avisar();
};

/** Vai para um endereço sem passar pela tela (o começo de cada teste). */
export function irPara(caminho: string) {
  trocaOriginal(null, "", caminho);
  avisar();
}

export const roteador = {
  refresh: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
};

let ultimaBusca = "";
let ultimosParametros = new URLSearchParams();

function parametrosDe(busca: string): URLSearchParams {
  if (busca !== ultimaBusca) {
    ultimaBusca = busca;
    ultimosParametros = new URLSearchParams(busca);
  }
  return ultimosParametros;
}

export const moduloDeNavegacao = {
  useSearchParams: () => parametrosDe(useSyncExternalStore(assinar, () => window.location.search, () => "")),
  usePathname: () => useSyncExternalStore(assinar, () => window.location.pathname, () => "/"),
  useRouter: () => roteador,
  notFound: () => {
    throw new Error("NEXT_HTTP_ERROR_FALLBACK;404");
  },
};
