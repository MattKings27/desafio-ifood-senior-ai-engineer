/**
 * O tema da tela: claro, escuro, ou o que o sistema dela disser.
 *
 * Três peças, que precisam concordar entre si:
 * - o SCRIPT_DO_TEMA, que roda no `<head>` antes da primeira pintura e marca
 *   `data-tema` no `<html>` (sem ele, a tela pisca clara antes de escurecer);
 * - a loja de preferência, que a escolha de tema da folha de Preferências
 *   (`componentes/globais/Preferencias.tsx`) lê e escreve;
 * - o CSS, que troca todos os tokens quando `data-tema="escuro"`.
 *
 * A preferência mora no `localStorage`, na chave `tema`. "Automático" não é
 * gravado como tema: é resolvido pelo `prefers-color-scheme` a cada vez, e
 * acompanha o sistema quando ele muda (o celular que escurece à noite).
 */

export type PreferenciaDeTema = "claro" | "escuro" | "automatico";
export type Tema = "claro" | "escuro";

export const CHAVE_DO_TEMA = "tema";
export const CONSULTA_ESCURO = "(prefers-color-scheme: dark)";

/** A cor da barra do navegador no celular: a do cabeçalho, em cada tema. */
export const COR_DA_BARRA: Readonly<Record<Tema, string>> = {
  claro: "#ffffff",
  escuro: "#1c1c1e",
};

export const PREFERENCIAS: readonly PreferenciaDeTema[] = ["claro", "escuro", "automatico"];

export function ehPreferencia(valor: unknown): valor is PreferenciaDeTema {
  return PREFERENCIAS.includes(valor as PreferenciaDeTema);
}

export function resolverTema(preferencia: PreferenciaDeTema, sistemaEscuro: boolean): Tema {
  if (preferencia === "automatico") return sistemaEscuro ? "escuro" : "claro";
  return preferencia;
}

/**
 * O script do `<head>`. É uma string porque roda antes do React existir.
 *
 * Tudo dentro de try/catch: `localStorage` pode não existir (navegação
 * anônima restrita, cookies bloqueados), e nesse caso fica o automático.
 */
export const SCRIPT_DO_TEMA = `(function(){try{var d=document.documentElement,p=null;try{p=localStorage.getItem(${JSON.stringify(
  CHAVE_DO_TEMA,
)})}catch(e){}if(p!=="claro"&&p!=="escuro")p="automatico";var t=p==="automatico"?(window.matchMedia&&window.matchMedia(${JSON.stringify(
  CONSULTA_ESCURO,
)}).matches?"escuro":"claro"):p;d.setAttribute("data-tema",t);var c=t==="escuro"?${JSON.stringify(
  COR_DA_BARRA.escuro,
)}:${JSON.stringify(
  COR_DA_BARRA.claro,
)};var m=document.querySelectorAll('meta[name="theme-color"]');if(!m.length){var n=document.createElement("meta");n.setAttribute("name","theme-color");document.head.appendChild(n);m=[n]}for(var i=0;i<m.length;i++)m[i].setAttribute("content",c)}catch(e){}})();`;

/* -------------------------------------------------------------------------- */
/* Leitura e aplicação                                                         */
/* -------------------------------------------------------------------------- */

export function lerPreferencia(): PreferenciaDeTema {
  try {
    const guardada = window.localStorage.getItem(CHAVE_DO_TEMA);
    return ehPreferencia(guardada) ? guardada : "automatico";
  } catch {
    return "automatico";
  }
}

function sistemaEstaEscuro(): boolean {
  try {
    return window.matchMedia(CONSULTA_ESCURO).matches;
  } catch {
    return false;
  }
}

/** Marca o tema no `<html>` e na barra do navegador. Devolve o tema aplicado. */
export function aplicarTema(preferencia: PreferenciaDeTema = lerPreferencia()): Tema {
  const tema = resolverTema(preferencia, sistemaEstaEscuro());
  const raiz = document.documentElement;
  if (raiz.getAttribute("data-tema") !== tema) raiz.setAttribute("data-tema", tema);

  // O Next escreve uma meta por media query (claro e escuro); todas passam a
  // dizer a cor do tema escolhido, senão a barra do navegador desobedece.
  let metas = Array.from(document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]'));
  if (metas.length === 0) {
    const meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
    metas = [meta];
  }
  for (const meta of metas) meta.setAttribute("content", COR_DA_BARRA[tema]);
  return tema;
}

export function temaAplicado(): Tema {
  return document.documentElement.getAttribute("data-tema") === "escuro" ? "escuro" : "claro";
}

/* -------------------------------------------------------------------------- */
/* Loja: para o React ler com useSyncExternalStore                             */
/* -------------------------------------------------------------------------- */

const ouvintes = new Set<() => void>();
let desligar: (() => void) | null = null;

function avisar() {
  for (const ouvinte of ouvintes) ouvinte();
}

function ligar(): () => void {
  const consulta = window.matchMedia?.(CONSULTA_ESCURO);
  const aoMudarSistema = () => {
    if (lerPreferencia() === "automatico") {
      aplicarTema("automatico");
      avisar();
    }
  };
  // Outra aba trocou o tema: esta acompanha, para as duas não discordarem.
  const aoMudarOutraAba = (evento: StorageEvent) => {
    if (evento.key !== CHAVE_DO_TEMA && evento.key !== null) return;
    aplicarTema();
    avisar();
  };
  consulta?.addEventListener?.("change", aoMudarSistema);
  window.addEventListener("storage", aoMudarOutraAba);
  return () => {
    consulta?.removeEventListener?.("change", aoMudarSistema);
    window.removeEventListener("storage", aoMudarOutraAba);
  };
}

/** Assina as mudanças de preferência (desta aba, de outra aba ou do sistema). */
export function assinarTema(ouvinte: () => void): () => void {
  ouvintes.add(ouvinte);
  desligar ??= ligar();
  return () => {
    ouvintes.delete(ouvinte);
    if (ouvintes.size === 0 && desligar) {
      desligar();
      desligar = null;
    }
  };
}

export function definirPreferencia(preferencia: PreferenciaDeTema): Tema {
  try {
    window.localStorage.setItem(CHAVE_DO_TEMA, preferencia);
  } catch {
    // Sem armazenamento, a escolha vale só nesta visita. Não é motivo de erro.
  }
  const tema = aplicarTema(preferencia);
  avisar();
  return tema;
}
