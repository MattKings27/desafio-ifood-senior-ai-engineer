/**
 * O `id_cliente` de uma escrita: gerado uma vez no navegador e repetido em cada
 * nova tentativa, para que "tentar de novo" nunca grave duas vezes.
 */
export function novoIdCliente(): string {
  const cripto = globalThis.crypto as Crypto | undefined;
  if (typeof cripto?.randomUUID === "function") return cripto.randomUUID();
  // Navegador sem randomUUID (contexto sem HTTPS): basta ser único nesta aba.
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
