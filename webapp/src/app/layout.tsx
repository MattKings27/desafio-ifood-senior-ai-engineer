import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";

import { BotaoConversa, PainelDaConversa } from "@/componentes/conversa";
import { BarraInferior } from "@/componentes/globais/BarraInferior";
import { Cabecalho } from "@/componentes/globais/Cabecalho";
import { Provedores } from "@/componentes/globais/Provedores";
import { LinkPular, Rodape } from "@/componentes/globais/Rodape";
import { ScriptDoTema } from "@/componentes/globais/ScriptDoTema";
import { COR_DA_BARRA } from "@/lib/tema";

import "./globals.css";

/**
 * As fontes do iFood chamam-se **`iFood RC Títulos`** e **`iFood RC Textos`**:
 * nomes medidos no portal do lojista, não inferidos. São proprietárias, e
 * nenhum arquivo delas é versionado aqui.
 *
 * A pilha em `globals.css` declara os nomes reais primeiro: quem tiver as fontes
 * instaladas vê a marca de verdade. Sora e Inter entram como a aproximação livre
 * para todo mundo: Sora pelos traços abertos dos títulos, Inter pela
 * legibilidade em número tabular, que é metade do que esta interface mostra.
 *
 * As duas vêm do próprio repositório (`fontes/`, licença OFL), não do Google
 * Fonts: com `next/font/google` o build baixava as fontes, e uma falha de rede
 * derrubou o build no CI. São variáveis: um arquivo cobre do 400 ao 700.
 */
const titulo = localFont({
  src: "./fontes/sora-latin-wght-normal.woff2",
  weight: "400 700",
  variable: "--fonte-titulo",
  display: "swap",
});

const corpo = localFont({
  src: "./fontes/inter-latin-wght-normal.woff2",
  weight: "400 700",
  variable: "--fonte-corpo",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Sabor da Maria", template: "%s | Sabor da Maria" },
  applicationName: "Sabor da Maria",
  description:
    "Consultoria de cardápio e precificação para o delivery da Dona Maria. " +
    "Todo número vem da planilha dela, com a conta aberta.",
};

/**
 * A cor da barra do navegador acompanha o tema. As duas metas por media query
 * valem sem JavaScript; com ele, o script do tema troca as duas para a cor do
 * tema que ela escolheu. `resizes-content` mantém a caixa de texto do chat
 * acima do teclado no celular.
 */
export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: COR_DA_BARRA.claro },
    { media: "(prefers-color-scheme: dark)", color: COR_DA_BARRA.escuro },
  ],
  interactiveWidget: "resizes-content",
};

export default function LayoutRaiz({ children }: { children: React.ReactNode }) {
  return (
    // O tema é marcado pelo script antes da pintura; o servidor não sabe qual é.
    <html lang="pt-BR" className={`${titulo.variable} ${corpo.variable}`} suppressHydrationWarning>
      <head>
        <ScriptDoTema />
      </head>
      <body className="flex min-h-dvh flex-col pb-[calc(var(--altura-barra-inferior)+env(safe-area-inset-bottom))] antialiased lg:pb-0">
        <Provedores>
          {/* Primeira parada do teclado: pular direto ao conteúdo. */}
          <LinkPular />
          <Cabecalho />
          {/* No celular a barra fica fixa embaixo, mas vem cedo na ordem do Tab. */}
          <BarraInferior />
          <main
            id="conteudo"
            tabIndex={-1}
            className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-10 focus:outline-none sm:px-6 lg:pt-8 lg:pb-24"
          >
            {children}
          </main>
          <Rodape />
          <BotaoConversa />
          <PainelDaConversa />
        </Provedores>
      </body>
    </html>
  );
}
