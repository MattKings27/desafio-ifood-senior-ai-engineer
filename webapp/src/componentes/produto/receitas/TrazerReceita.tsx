"use client";

/**
 * "Trazer uma receita": ela cola o endereço de uma página de receita, o
 * servidor lê a página e a receita entra no catálogo, já conferida com a
 * despensa e a cozinha dela.
 *
 * Os estados do campo: vazio; endereço que não parece de página (avisado
 * antes de ir ao servidor); lendo a página (pode levar alguns segundos);
 * trouxe (nova, ou uma que já estava aqui), dizendo em que aba ela entrou; e a
 * recusa da página sem receita, com a pergunta do servidor.
 */

import { ArrowRight, CheckCircle, LinkSimple } from "@phosphor-icons/react/dist/ssr";
import type { FormEvent } from "react";
import { useRef, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { Campo, Entrada } from "@/componentes/compartilhados/Campos";
import { Folha } from "@/componentes/compartilhados/Folha";
import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import type { ReceitaTrazidaNaTela } from "@/lib/acoes/receitas";
import { trazerReceita } from "@/lib/acoes/receitas";
import { useAcao } from "@/lib/dados/useAcao";
import { MENSAGENS } from "@/lib/api/base";
import { textoParaEla } from "@/lib/formato";

import { CLASSES_DO_TOM, TOM_DA_COZINHA, comMaiuscula, ondeEntrou } from "./textos";

const ENDERECO = /^https?:\/\/[^\s/]+\.[^\s]+$/i;

function Trazida({ receita, aoTrazerOutra }: { receita: ReceitaTrazidaNaTela; aoTrazerOutra: () => void }) {
  const tom = CLASSES_DO_TOM[TOM_DA_COZINHA[receita.cozinha.codigo]];
  return (
    <div className="space-y-4">
      <p role="status" className="flex items-start gap-2 text-base font-semibold text-tinta">
        <CheckCircle size={22} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-sucesso" />
        {receita.nova ? `Trouxe ${receita.nome}.` : `${receita.nome} já estava aqui.`}
      </p>
      <div className="flex gap-3 rounded-md border border-borda p-3">
        <div className="w-20 shrink-0 overflow-hidden rounded-sm">
          <ImagemComFallback src={receita.imagem?.url} alt="" proporcao="1/1" tipo="receita" />
        </div>
        <div className="min-w-0 space-y-1">
          <p className="font-bold text-tinta">{receita.nome}</p>
          {receita.site ? <p className="text-sm text-apagado">{receita.site}</p> : null}
          <p className={`text-sm font-semibold ${tom.texto}`}>{receita.cozinha.rotulo}</p>
        </div>
      </div>
      <p className="text-sm text-texto">{ondeEntrou(receita.cozinha, receita.gosta)}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <BotaoLink href={receita.rota} iconeDepois={<ArrowRight size={18} weight="bold" />}>
          Ver a receita
        </BotaoLink>
        <Botao variante="terciario" onClick={aoTrazerOutra}>
          Trazer outra
        </Botao>
      </div>
    </div>
  );
}

export function TrazerReceita({ aberta, aoFechar }: { aberta: boolean; aoFechar: () => void }) {
  const [endereco, setEndereco] = useState("");
  const [recusa, setRecusa] = useState<string | null>(null);
  const [trazida, setTrazida] = useState<ReceitaTrazidaNaTela | null>(null);
  // Num ref, e não no estado: o fechar da folha pode ser o de um render
  // anterior, e mesmo assim tem que saber que a receita já veio.
  const trouxe = useRef(false);
  const { executar, pendente } = useAcao(trazerReceita, { avisarErro: false });

  const recomecar = () => {
    trouxe.current = false;
    setEndereco("");
    setRecusa(null);
    setTrazida(null);
  };

  // Fechar depois de trazer deixa a folha pronta para a próxima; fechar no meio
  // da digitação guarda o que ela escreveu.
  const fechar = () => {
    if (trouxe.current) recomecar();
    aoFechar();
  };

  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    if (pendente) return;
    const limpo = endereco.trim();
    if (!ENDERECO.test(limpo)) {
      setRecusa(
        limpo
          ? "Esse endereço não parece de uma página. Copie o endereço inteiro, que começa com https://."
          : "Cole o endereço da página da receita.",
      );
      return;
    }
    setRecusa(null);
    const resultado = await executar(limpo);
    if (resultado.ok) {
      trouxe.current = true;
      setTrazida(resultado.dados);
      return;
    }
    const { pergunta, mensagem } = resultado.erro;
    setRecusa(comMaiuscula(pergunta ?? textoParaEla(mensagem, MENSAGENS.semMotivo)));
  };

  return (
    <Folha
      aberto={aberta}
      aoFechar={fechar}
      titulo="Trazer uma receita"
      descricao="Cole o endereço de uma receita da internet. Eu leio a página e confiro com a despensa e a cozinha da senhora."
      focoInicial="#endereco-da-receita"
    >
      {trazida ? (
        <Trazida receita={trazida} aoTrazerOutra={recomecar} />
      ) : (
        <form onSubmit={enviar} noValidate className="space-y-4">
          <Campo
            id="endereco-da-receita"
            rotulo="Endereço da receita"
            dica="Pode ser do TudoGostoso, do Panelinha ou de outro site de receitas."
            erro={recusa}
          >
            <Entrada
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              value={endereco}
              onChange={(evento) => {
                setEndereco(evento.target.value);
                setRecusa(null);
              }}
              placeholder="https://www.tudogostoso.com.br/receita/..."
            />
          </Campo>
          <Botao
            type="submit"
            larguraTotal
            icone={<LinkSimple size={18} weight="bold" />}
            carregando={pendente}
            rotuloCarregando="Lendo a página…"
          >
            Trazer
          </Botao>
          {pendente ? (
            <p role="status" className="text-sm text-apagado">
              Lendo a página. Pode levar alguns segundos.
            </p>
          ) : null}
        </form>
      )}
    </Folha>
  );
}
