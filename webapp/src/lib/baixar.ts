/**
 * Baixar um arquivo da API para o aparelho dela: a despensa em texto, a cópia
 * de tudo.
 *
 * Um link comum (`<a download>`) não serve quando a rota pode não existir: o
 * navegador abriria uma página de erro no lugar do arquivo. Aqui o pedido vai
 * pelo mesmo caminho das outras leituras (tempo limite, erro com categoria), e
 * só o que chegou bem vira arquivo.
 */

import type { CategoriaDeErro } from "@/lib/api/base";
import { ErroDoMotor, MENSAGENS, buscar, erroDaResposta } from "@/lib/api/base";

export type ResultadoDoDownload =
  | { ok: true; nome: string }
  | { ok: false; categoria: CategoriaDeErro; mensagem: string };

/** Um arquivo grande (a cópia de tudo) pode levar mais que uma leitura comum. */
export const TEMPO_DO_DOWNLOAD_MS = 60_000;

/** O nome que a API sugere (`Content-Disposition`), sem pasta e sem caractere estranho. */
export function nomeDoArquivo(cabecalho: string | null | undefined): string | null {
  if (!cabecalho) return null;
  let bruto: string | null = null;
  const codificado = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(cabecalho);
  if (codificado?.[1]) {
    try {
      bruto = decodeURIComponent(codificado[1].trim());
    } catch {
      bruto = null;
    }
  }
  bruto ??= /filename\s*=\s*"?([^";]+)"?/.exec(cabecalho)?.[1]?.trim() ?? null;
  const nome = bruto?.split(/[\\/]/).pop()?.replace(/[^\p{L}\p{N}._ -]/gu, "").trim();
  return nome ? nome : null;
}

/** Entrega o conteúdo ao navegador como um arquivo para salvar. */
export function salvarArquivo(conteudo: Blob, nome: string): void {
  const url = URL.createObjectURL(conteudo);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // O navegador já começou a salvar; depois de um instante a memória volta.
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

/** Busca `caminho` na API e salva como arquivo. Nunca lança: devolve o que aconteceu. */
export async function baixarDaApi(caminho: string, nomePadrao: string): Promise<ResultadoDoDownload> {
  try {
    const resposta = await buscar(caminho, { tempoLimiteMs: TEMPO_DO_DOWNLOAD_MS });
    if (!resposta.ok) throw await erroDaResposta(resposta);
    const conteudo = await resposta.blob();
    const nome = nomeDoArquivo(resposta.headers.get("Content-Disposition")) ?? nomePadrao;
    salvarArquivo(conteudo, nome);
    return { ok: true, nome };
  } catch (causa) {
    if (causa instanceof ErroDoMotor) return { ok: false, categoria: causa.categoria, mensagem: causa.message };
    return { ok: false, categoria: "rede", mensagem: MENSAGENS.rede };
  }
}
