/**
 * O histórico do motor falso: as atividades de `atividades.json`, com a busca,
 * os filtros (categoria, quem, dia) e o cursor da API de verdade. A página é
 * pequena (6) para o "Ver mais" aparecer com o exemplo do contrato.
 */

const PAGINA = 6;

function semAcento(texto) {
  return String(texto)
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

function agrupar(itens, rotulos) {
  const grupos = [];
  for (const item of itens) {
    const ultimo = grupos.at(-1);
    if (ultimo && ultimo.dia === item.dia) ultimo.itens.push(item);
    else grupos.push({ dia: item.dia, rotulo: rotulos.get(item.dia) ?? item.dia, itens: [item] });
  }
  return grupos;
}

export function rotasDoHistorico({ rota, ok, recusa, atividades }) {
  rota("GET", /^\/api\/atividades$/, (_req, res, { url }) => {
    const base = atividades();
    const parametro = (nome) => url.searchParams.get(nome) ?? "";
    const [q, categoria, quem, dia, cursor] = ["q", "categoria", "quem", "dia", "cursor"].map(parametro);
    if (categoria && !base.categorias.some((c) => c.id === categoria)) {
      return recusa(res, 200, "uso", "Essa categoria não existe.");
    }
    const rotulos = new Map(base.grupos.map((g) => [g.dia, g.rotulo]));
    const todos = base.grupos.flatMap((g) => g.itens);
    const semODia = todos.filter(
      (item) =>
        (!categoria || item.categoria === categoria) &&
        (!quem || item.quem === quem) &&
        (!q || semAcento(item.texto).includes(semAcento(q))),
    );
    const filtrados = semODia.filter((item) => !dia || item.dia === dia);
    const limite = Number(parametro("limite")) || PAGINA;
    const inicio = cursor ? filtrados.findIndex((item) => item.id === cursor) + 1 : 0;
    const fatia = filtrados.slice(inicio, inicio + limite);
    const temMais = inicio + limite < filtrados.length;
    const dias = [...new Set(semODia.map((item) => item.dia))].map((id) => ({ id, rotulo: rotulos.get(id) ?? id }));
    ok(res, {
      ...base,
      grupos: agrupar(fatia, rotulos),
      total: filtrados.length,
      texto: filtrados.length === 0 ? "nada por aqui ainda" : `${filtrados.length} ${filtrados.length === 1 ? "registro" : "registros"}`,
      proximo_cursor: temMais && fatia.length ? fatia.at(-1).id : null,
      dias,
    });
  });
}
