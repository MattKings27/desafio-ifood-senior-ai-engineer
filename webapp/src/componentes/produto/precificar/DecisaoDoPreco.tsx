"use client";

/**
 * A decisão dela: cobrar o preço do controle, pensar mais, ou deixar o prato
 * de fora. O preço de um dos três caminhos se escolhe no próprio caminho. A
 * decisão vai para o cardápio, e a frase que volta é a da API. Enquanto a
 * cozinha espera a confirmação dela, o "Vou cobrar" fica desabilitado e aponta
 * o que falta; pensar mais e deixar de fora valem sempre.
 */

import { ListChecks } from "@phosphor-icons/react/dist/ssr";

import { Botao } from "@/componentes/compartilhados/Botao";
import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { Card } from "@/componentes/compartilhados/Card";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import type { DecisaoRegistrada } from "@/lib/api/cardapio";
import type { PontoPreco } from "@/lib/api/preco";

export function DecisaoDoPreco({
  ponto,
  registrada,
  erro,
  ocupado,
  aoDecidir,
  idDoBloqueio,
}: {
  /** O preço que o controle mostra agora, com a conta da API. */
  ponto: PontoPreco | null;
  registrada: DecisaoRegistrada | null;
  erro: string | null;
  ocupado: boolean;
  aoDecidir: (decisao: "aceito" | "recusado" | "adiado", preco?: number) => void;
  /** Enquanto o aceite espera (a cozinha a confirmar), o id do que falta: só o "Vou cobrar" espera. */
  idDoBloqueio?: string;
}) {
  if (registrada) {
    return (
      <Card tom="secao" aria-labelledby="titulo-da-decisao" role="status" className="space-y-2">
        <h2 id="titulo-da-decisao" className="font-bold text-tinta">
          Anotado
        </h2>
        <p className="text-base text-texto">{registrada.texto}</p>
        {registrada.aviso ? <p className="text-sm text-perigo">{registrada.aviso}</p> : null}
        <BotaoLink href="/cardapio" variante="secundario" tamanho="sm" icone={<ListChecks size={18} weight="bold" />}>
          Ver o cardápio
        </BotaoLink>
      </Card>
    );
  }
  return (
    <Card aria-labelledby="titulo-da-decisao">
      <TituloSecao
        id="titulo-da-decisao"
        titulo="E então, qual preço a senhora escolhe?"
        apoio="A decisão é da senhora. Eu só mostrei as contas."
      />
      <div className="flex flex-col gap-2 min-[560px]:flex-row min-[560px]:flex-wrap">
        {ponto ? (
          <Botao
            className="aria-disabled:opacity-50 aria-disabled:hover:bg-marca-fundo"
            carregando={ocupado}
            rotuloCarregando="Anotando…"
            aria-disabled={idDoBloqueio ? true : undefined}
            aria-describedby={idDoBloqueio}
            onClick={() => {
              if (!idDoBloqueio) aoDecidir("aceito", ponto.preco.valor);
            }}
          >
            Vou cobrar {ponto.preco.texto}
          </Botao>
        ) : null}
        <Botao variante="terciario" disabled={ocupado} onClick={() => aoDecidir("adiado")}>
          Deixa eu pensar
        </Botao>
        <Botao variante="texto" disabled={ocupado} onClick={() => aoDecidir("recusado")}>
          Esse prato não
        </Botao>
      </div>
      {erro ? (
        <p role="alert" className="mt-2 text-sm font-medium text-perigo">
          {erro}
        </p>
      ) : null}
    </Card>
  );
}
