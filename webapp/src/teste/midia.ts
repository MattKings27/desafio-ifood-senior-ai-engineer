/**
 * `matchMedia` controlável nos testes.
 *
 * O jsdom não implementa `matchMedia`. Este dublê guarda quais consultas estão
 * ligadas e avisa os ouvintes quando uma muda, que é o que o tema automático e
 * o `reducedMotion` do motion precisam para serem testados de verdade.
 */

type Ouvinte = (evento: MediaQueryListEvent) => void;

const ligadas = new Set<string>();
const ouvintes = new Map<string, Set<Ouvinte>>();

function listaPara(consulta: string): MediaQueryList {
  const doConjunto = () => {
    let conjunto = ouvintes.get(consulta);
    if (!conjunto) {
      conjunto = new Set();
      ouvintes.set(consulta, conjunto);
    }
    return conjunto;
  };
  return {
    get matches() {
      return ligadas.has(consulta);
    },
    media: consulta,
    onchange: null,
    addEventListener: (_tipo: string, ouvinte: Ouvinte) => doConjunto().add(ouvinte),
    removeEventListener: (_tipo: string, ouvinte: Ouvinte) => doConjunto().delete(ouvinte),
    addListener: (ouvinte: Ouvinte) => doConjunto().add(ouvinte),
    removeListener: (ouvinte: Ouvinte) => doConjunto().delete(ouvinte),
    dispatchEvent: () => true,
  } as unknown as MediaQueryList;
}

export function instalarMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (consulta: string) => listaPara(consulta),
  });
}

/** Liga ou desliga uma consulta, avisando quem a escuta. */
export function definirMidia(consulta: string, ligada: boolean) {
  if (ligada) ligadas.add(consulta);
  else ligadas.delete(consulta);
  for (const ouvinte of ouvintes.get(consulta) ?? []) {
    ouvinte({ matches: ligada, media: consulta } as MediaQueryListEvent);
  }
}

/** Quantos ouvintes a consulta tem: serve para provar que ninguém vaza. */
export function ouvintesDe(consulta: string): number {
  return ouvintes.get(consulta)?.size ?? 0;
}

export function reiniciarMidia() {
  ligadas.clear();
  ouvintes.clear();
}

/** O sistema dela está no escuro? */
export function sistemaEscuro(ligado: boolean) {
  definirMidia("(prefers-color-scheme: dark)", ligado);
}
