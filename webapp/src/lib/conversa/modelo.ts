/**
 * Quem responde na conversa, dito para ela: o nome do modelo em palavras
 * ("Claude Fable 5.1"), nunca o identificador de programa
 * (`claude-fable-5-1`). Sem o nome, uma frase neutra.
 */

/** `claude-fable-5-1` → "Claude Fable 5.1"; `claude-sonnet-4-5-20250929` → "Claude Sonnet 4.5". */
export function nomeDoModelo(id: string | null | undefined): string | null {
  const limpo = id?.trim().toLowerCase().replace(/^[a-z]+\//, "");
  if (!limpo || limpo.length > 80 || !/^[a-z][a-z0-9.-]*$/.test(limpo)) return null;
  const palavras: string[] = [];
  for (const parte of limpo.split("-")) {
    // A data de publicação (20250929) não diz nada para ela.
    if (!parte || /^\d{8}$/.test(parte)) continue;
    const anterior = palavras.at(-1);
    if (/^\d+$/.test(parte) && anterior && /^\d+(?:\.\d+)*$/.test(anterior)) {
      palavras[palavras.length - 1] = `${anterior}.${parte}`;
      continue;
    }
    palavras.push(/^\d/.test(parte) ? parte : parte.charAt(0).toUpperCase() + parte.slice(1));
  }
  return palavras.length > 0 ? palavras.join(" ") : null;
}

export const FRASE_SEM_MODELO =
  "Quem conversa com a senhora é um modelo de inteligência artificial. Ele entende o que a senhora escreve, mas as contas não saem da cabeça dele.";

/** A frase de "Sobre o agente": quem responde, do jeito dela. */
export function fraseDoModelo(id: string | null | undefined): string {
  const nome = nomeDoModelo(id);
  if (!nome) return FRASE_SEM_MODELO;
  if (/^Claude\b/.test(nome)) {
    return `Quem conversa com a senhora é o ${nome}, um modelo de inteligência artificial da Anthropic.`;
  }
  return `Quem conversa com a senhora é o modelo ${nome}, de inteligência artificial.`;
}
