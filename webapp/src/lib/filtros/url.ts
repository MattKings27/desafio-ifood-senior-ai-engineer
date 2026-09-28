/**
 * Filtros de lista guardados na URL: `/receitas?veredito=APTO&tempo_max=40`.
 *
 * A URL é a fonte: recarregar, voltar e mandar o link para alguém mostram a
 * mesma lista. Mudar um filtro troca a URL com `history.replaceState`, que o
 * Next acompanha (`useSearchParams` atualiza) sem ida ao servidor. A lista em
 * si é filtrada no navegador sobre o que já veio, comparando `.valor`, nunca
 * fazendo conta com ele.
 *
 * Este arquivo é puro e serve também no servidor (a página lê `searchParams`
 * e pede a lista já filtrada à API). O hook do navegador fica em
 * `@/lib/dados/useFiltrosNaUrl`.
 */

export type CampoDeFiltro =
  | { tipo: "texto"; padrao?: string }
  | { tipo: "lista" }
  | { tipo: "numero"; padrao?: number | null }
  | { tipo: "booleano"; padrao?: boolean }
  | { tipo: "opcao"; opcoes: readonly string[]; padrao: string };

export type EsquemaDeFiltros = Readonly<Record<string, CampoDeFiltro>>;

export type ValorDoCampo<C extends CampoDeFiltro> = C extends { tipo: "texto" }
  ? string
  : C extends { tipo: "lista" }
    ? string[]
    : C extends { tipo: "numero" }
      ? number | null
      : C extends { tipo: "booleano" }
        ? boolean
        : C extends { tipo: "opcao"; opcoes: readonly (infer O)[] }
          ? O
          : never;

export type FiltrosDe<E extends EsquemaDeFiltros> = { [K in keyof E]: ValorDoCampo<E[K]> };

type ParametrosLidos = Pick<URLSearchParams, "get" | "getAll">;

function padraoDe(campo: CampoDeFiltro): unknown {
  switch (campo.tipo) {
    case "texto":
      return campo.padrao ?? "";
    case "lista":
      return [];
    case "numero":
      return campo.padrao ?? null;
    case "booleano":
      return campo.padrao ?? false;
    case "opcao":
      return campo.padrao;
  }
}

function lerCampo(parametros: ParametrosLidos, chave: string, campo: CampoDeFiltro): unknown {
  switch (campo.tipo) {
    case "texto":
      return parametros.get(chave) ?? padraoDe(campo);
    case "lista":
      return parametros
        .getAll(chave)
        .flatMap((valor) => valor.split(","))
        .map((valor) => valor.trim())
        .filter(Boolean);
    case "numero": {
      const bruto = parametros.get(chave);
      const numero = bruto === null || bruto.trim() === "" ? Number.NaN : Number(bruto);
      return Number.isFinite(numero) ? numero : padraoDe(campo);
    }
    case "booleano": {
      const bruto = parametros.get(chave);
      if (bruto === "true" || bruto === "1") return true;
      if (bruto === "false" || bruto === "0") return false;
      return padraoDe(campo);
    }
    case "opcao": {
      const bruto = parametros.get(chave);
      return bruto !== null && campo.opcoes.includes(bruto) ? bruto : campo.padrao;
    }
  }
}

export function lerFiltros<E extends EsquemaDeFiltros>(
  parametros: ParametrosLidos,
  esquema: E,
): FiltrosDe<E> {
  const filtros: Record<string, unknown> = {};
  for (const [chave, campo] of Object.entries(esquema)) {
    filtros[chave] = lerCampo(parametros, chave, campo);
  }
  return filtros as FiltrosDe<E>;
}

function ehPadrao(campo: CampoDeFiltro, valor: unknown): boolean {
  if (campo.tipo === "lista") return !Array.isArray(valor) || valor.length === 0;
  if (campo.tipo === "texto") return typeof valor !== "string" || valor.trim() === "" || valor === padraoDe(campo);
  return valor === padraoDe(campo) || valor === undefined;
}

/**
 * Escreve os filtros sobre os parâmetros de `base`, sem apagar os que não são
 * filtro (ex.: `?aba=`). Valor padrão sai da URL: a URL limpa é a lista inteira.
 */
export function escreverFiltros<E extends EsquemaDeFiltros>(
  filtros: Partial<FiltrosDe<E>>,
  esquema: E,
  base: URLSearchParams = new URLSearchParams(),
): URLSearchParams {
  const saida = new URLSearchParams(base);
  for (const [chave, valor] of Object.entries(filtros)) {
    const campo = esquema[chave];
    if (!campo) continue;
    saida.delete(chave);
    if (ehPadrao(campo, valor)) continue;
    if (campo.tipo === "lista") {
      for (const item of valor as string[]) saida.append(chave, item);
    } else {
      saida.set(chave, String(typeof valor === "string" ? valor.trim() : valor));
    }
  }
  return saida;
}

/** Quantos filtros estão fora do padrão: o "(2)" do botão Filtros. */
export function contarAtivos<E extends EsquemaDeFiltros>(
  filtros: FiltrosDe<E>,
  esquema: E,
  ignorar: readonly (keyof E)[] = [],
): number {
  return Object.entries(esquema).filter(
    ([chave, campo]) => !ignorar.includes(chave) && !ehPadrao(campo, filtros[chave]),
  ).length;
}
