/**
 * Leitura das fixtures de contrato e de arquivos do repositório nos testes.
 *
 * O vitest roda na raiz do `webapp`; os contratos moram na raiz do repositório.
 * (`import.meta.url` não serve: sob jsdom ele é `http:`, não `file:`.)
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/** Caminho absoluto a partir da raiz do repositório. */
export function doRepositorio(...partes: string[]): string {
  return resolve(process.cwd(), "..", ...partes);
}

/** Caminho absoluto a partir da raiz do `webapp`. */
export function doWebapp(...partes: string[]): string {
  return resolve(process.cwd(), ...partes);
}

/** O `dados` de uma rota, como o contrato em `contratos/web/` o fixa. */
export function contrato<T = unknown>(arquivo: string): T {
  return JSON.parse(readFileSync(doRepositorio("contratos", "web", arquivo), "utf-8")) as T;
}

/** Os eventos de um `.jsonl` de contrato, um objeto por linha. */
export function eventosDoContrato<T = unknown>(arquivo: string): T[] {
  return readFileSync(doRepositorio("contratos", "web", arquivo), "utf-8")
    .split("\n")
    .filter((linha) => linha.trim() !== "")
    .map((linha) => JSON.parse(linha) as T);
}
