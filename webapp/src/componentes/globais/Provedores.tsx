"use client";

/**
 * Os provedores do layout raiz, na ordem em que dependem um do outro:
 * movimento (LazyMotion + "reduzir movimento"), avisos, sincronização entre
 * superfícies e a conversa. Moram no layout, então sobrevivem à navegação.
 */

import type { ReactNode } from "react";
import { useLayoutEffect } from "react";

import { ProvedorDeMovimento } from "@/componentes/compartilhados/Movimento";
import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import { ProvedorDaConversa } from "@/componentes/conversa";
import { ProvedorDeSincronizacao } from "@/lib/dados/sincronizacao";
import { aplicarAparencia } from "@/lib/preferencias";
import { aplicarTema } from "@/lib/tema";

export function Provedores({ children }: { children: ReactNode }) {
  // Em desenvolvimento, o modo estrito do React remonta a raiz e limpa os
  // atributos que o script do <head> pôs no <html>. Aplicar de novo antes da
  // pintura evita o piscar; em produção, não muda nada.
  useLayoutEffect(() => {
    aplicarTema();
    aplicarAparencia();
  }, []);

  return (
    <ProvedorDeMovimento>
      <ProvedorDeToasts>
        <ProvedorDeSincronizacao>
          <ProvedorDaConversa>{children}</ProvedorDaConversa>
        </ProvedorDeSincronizacao>
      </ProvedorDeToasts>
    </ProvedorDeMovimento>
  );
}
