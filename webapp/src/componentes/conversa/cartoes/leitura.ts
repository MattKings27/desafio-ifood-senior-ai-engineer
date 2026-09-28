/**
 * Leitura segura dos `dados` de um card.
 *
 * O `dados` tem a forma da rota do card (`ref.rota`), mas chega como `unknown`:
 * o backend pode mandar só o mínimo (enquanto a rota não existe), um campo
 * pode vir `null` (item sem preço, cobertura sem o peso da embalagem), e um
 * card novo pode vir com campos que a tela ainda não conhece. Cada leitura
 * aqui devolve o valor certo ou `null`, e o card mostra o que tiver.
 */

import type { Dinheiro, Imagem } from "@/lib/api/base";
import { ehImagemDaApi } from "@/lib/api/base";
import { linkSeguro } from "@/lib/conversa/markdown";
import type { Veredito } from "@/lib/formato";
import { ROTULO_DO_VEREDITO } from "@/lib/formato";

export type Solto = Record<string, unknown>;

export function obj(valor: unknown): Solto | null {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor) ? (valor as Solto) : null;
}

export function lista(valor: unknown): unknown[] {
  return Array.isArray(valor) ? valor : [];
}

/** Os objetos de uma lista (o resto é descartado). */
export function objetos(valor: unknown): Solto[] {
  return lista(valor).map(obj).filter((item): item is Solto => item !== null);
}

/** Texto não vazio, sem espaços sobrando. */
export function str(valor: unknown): string | null {
  if (typeof valor !== "string") return null;
  const limpo = valor.trim();
  return limpo ? limpo : null;
}

export function num(valor: unknown): number | null {
  return typeof valor === "number" && Number.isFinite(valor) ? valor : null;
}

export function bool(valor: unknown): boolean | null {
  return typeof valor === "boolean" ? valor : null;
}

/** Dinheiro com o texto da API. Sem texto, não é dinheiro que dê para mostrar. */
export function dinheiro(valor: unknown): Dinheiro | null {
  const bruto = obj(valor);
  const texto = str(bruto?.texto);
  if (!bruto || !texto) return null;
  return { valor: num(bruto.valor) ?? Number.NaN, texto };
}

/** Só a foto que a API serve (`/motor/imagens/<chave>`). */
export function imagem(valor: unknown): Exclude<Imagem, null> | null {
  const bruto = obj(valor);
  const url = str(bruto?.url);
  if (!bruto || !url || !ehImagemDaApi(url)) return null;
  return { url, credito: str(bruto.credito) ?? "" };
}

/** Um caminho da própria interface ("/receitas/arroz-com-frango"), nunca outro endereço. */
export function rotaInterna(valor: unknown): string | null {
  const rota = str(valor);
  if (!rota || !rota.startsWith("/") || rota.startsWith("//") || rota.startsWith("/\\")) return null;
  if (rota.startsWith("/api/") || rota.startsWith("/motor/")) return null;
  return /^\/[A-Za-z0-9\-._~%/?=&#+]*$/.test(rota) ? rota : null;
}

/** Um endereço de fora (a fonte de uma receita, de um preço de mercado): só http e https. */
export function urlExterna(valor: unknown): string | null {
  const url = str(valor);
  return url ? linkSeguro(url) : null;
}

const VEREDITOS = Object.keys(ROTULO_DO_VEREDITO) as Veredito[];

export function veredito(valor: unknown): Veredito | null {
  return VEREDITOS.find((v) => v === valor) ?? null;
}

/** O parâmetro do card (`ref.parametros.prato`, `.preco`…), quando o backend manda. */
export function parametro(cartao: { ref: { parametros?: Record<string, unknown> } }, nome: string): unknown {
  return cartao.ref.parametros?.[nome];
}
