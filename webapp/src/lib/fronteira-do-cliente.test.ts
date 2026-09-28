/**
 * A fronteira entre servidor e navegador. Um módulo sem "use client" pode ser
 * renderizado no servidor; se ele chamar uma função que mora num módulo com
 * "use client", o Next derruba a página ("Attempted to call ... from the
 * server"). Componente (nome com maiúscula) e tipo atravessam a fronteira; função
 * não. Este teste lê os imports de todo módulo de `src` e reprova a função que
 * atravessa, antes que ela chegue à tela.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const SRC = path.resolve(__dirname, "..");
const IMPORT = /import\s+(type\s+)?\{([^}]*)\}\s+from\s+"([^"]+)"/g;

function modulos(pasta: string): string[] {
  return readdirSync(pasta).flatMap((nome) => {
    const caminho = path.join(pasta, nome);
    if (statSync(caminho).isDirectory()) return modulos(caminho);
    return /\.(ts|tsx)$/.test(nome) && !/\.test\.(ts|tsx)$/.test(nome) ? [caminho] : [];
  });
}

function doCliente(caminho: string): boolean {
  return /^\s*(\/\*[\s\S]*?\*\/\s*|\/\/[^\n]*\n\s*)*["']use client["']/.test(readFileSync(caminho, "utf-8"));
}

function resolver(origem: string, alvo: string): string | null {
  const base = alvo.startsWith("@/") ? path.join(SRC, alvo.slice(2)) : alvo.startsWith(".") ? path.resolve(path.dirname(origem), alvo) : null;
  if (!base) return null;
  for (const final of [".tsx", ".ts", "/index.tsx", "/index.ts", ""]) {
    const candidato = base + final;
    if (existsSync(candidato) && statSync(candidato).isFile()) return candidato;
  }
  return null;
}

function funcoesQueAtravessam(caminho: string): string[] {
  if (doCliente(caminho)) return [];
  const texto = readFileSync(caminho, "utf-8");
  const achados: string[] = [];
  for (const [, soTipo, nomes, alvo] of texto.matchAll(IMPORT)) {
    if (soTipo || !nomes || !alvo) continue;
    const destino = resolver(caminho, alvo);
    if (!destino || !doCliente(destino)) continue;
    for (const bruto of nomes.split(",")) {
      const nome = bruto.trim();
      if (!nome || nome.startsWith("type ")) continue;
      const importado = nome.split(/\s+as\s+/)[0]!.trim();
      if (/^[a-z]/.test(importado)) achados.push(`${path.relative(SRC, caminho)} importa ${importado} de ${alvo}`);
    }
  }
  return achados;
}

describe("a fronteira entre servidor e navegador", () => {
  it("nenhum módulo do servidor chama função de um módulo do navegador", () => {
    expect(modulos(SRC).flatMap(funcoesQueAtravessam)).toEqual([]);
  }, 60_000);
});
