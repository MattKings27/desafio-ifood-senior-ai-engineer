"use client";

/**
 * Quando até o layout raiz falha. O Next troca o documento inteiro por este,
 * sem o CSS global nem o script do layout: por isso ele importa o CSS e traz o
 * mesmo script do `<head>`, que marca o tema, o tamanho do texto e o movimento
 * antes da primeira pintura (sem ele, a página de erro piscava clara no tema
 * escuro). O efeito de layout repete a marcação quando o erro acontece depois
 * de a página já estar aberta, e o script não roda de novo.
 */

import { useEffect, useLayoutEffect } from "react";

import { Problema } from "@/componentes/compartilhados/Problema";
import { ScriptDoTema } from "@/componentes/globais/ScriptDoTema";
import { aplicarAparencia } from "@/lib/preferencias";
import { aplicarTema } from "@/lib/tema";

import "./globals.css";

export default function ErroGeral({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useLayoutEffect(() => {
    aplicarTema();
    aplicarAparencia();
  }, []);
  useEffect(() => {
    console.error("o aplicativo não abriu", error.digest ?? error);
  }, [error]);

  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <ScriptDoTema />
      </head>
      <body className="min-h-dvh bg-fundo text-texto antialiased">
        <title>Sabor da Maria</title>
        <main className="mx-auto max-w-xl px-4 py-16">
          <Problema
            categoria="rede"
            titulo="Não consegui abrir o Sabor da Maria"
            nivelTitulo={1}
            anunciar="alert"
            aoTentarDeNovo={retry}
          />
        </main>
      </body>
    </html>
  );
}
