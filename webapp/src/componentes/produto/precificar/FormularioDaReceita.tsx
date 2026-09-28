"use client";

/**
 * "Qual prato?": o endereço de uma receita da internet, ou a receita do jeito
 * que ela faz. O tempo no fogo é opcional: sem ele, a conferência pergunta, e a
 * resposta volta para este campo.
 */

import { ArrowRight, DownloadSimple } from "@phosphor-icons/react/dist/ssr";
import type { FormEvent } from "react";
import { useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { AreaDeTexto, Campo, Entrada, EntradaNumero } from "@/componentes/compartilhados/Campos";
import { Card } from "@/componentes/compartilhados/Card";
import { TituloSecao } from "@/componentes/compartilhados/Titulos";
import { ErroDoMotor } from "@/lib/api/base";
import { receitasDeHoje } from "@/lib/api/receitas";
import { textoParaEla } from "@/lib/formato";
import { EXEMPLO_DE_INGREDIENTES } from "@/lib/receita";

import type { Rascunho } from "./rascunho";
import { rascunhoDe } from "./rascunho";

/** Os ids dos campos que a conferência manda preencher. */
export const ID_DO_PREPARO = "campo-do-preparo";
export const ID_DO_RENDIMENTO = "campo-do-rendimento";
export const ID_DO_TEMPO = "campo-do-tempo";

function TrazerDaInternet({ aoTrazer }: { aoTrazer: (rascunho: Rascunho, aviso: string) => void }) {
  const [endereco, setEndereco] = useState("");
  const [trazendo, setTrazendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const trazer = async (evento: FormEvent) => {
    evento.preventDefault();
    if (!endereco.trim()) {
      setErro("Cole o endereço da receita, que começa com https://.");
      return;
    }
    setTrazendo(true);
    setErro(null);
    try {
      const { receita, procedencia } = await receitasDeHoje.receitaDaWeb(endereco.trim());
      const aviso = receita.rendimento_informado
        ? `Receita do ${procedencia.fonte}. Confira as linhas antes de seguir.`
        : `Receita do ${procedencia.fonte}. O site não diz quantas porções rende: preencha abaixo.`;
      aoTrazer({ ...rascunhoDe(receita), origem: { url: procedencia.url, fonte: procedencia.fonte } }, aviso);
    } catch (causa) {
      const mensagem = causa instanceof ErroDoMotor ? causa.message : null;
      setErro(textoParaEla(mensagem, "Não consegui trazer essa receita. Confira o endereço e tente de novo."));
    } finally {
      setTrazendo(false);
    }
  };

  return (
    <form noValidate onSubmit={trazer} className="flex flex-col gap-2 min-[560px]:flex-row min-[560px]:items-end">
      <Campo rotulo="Endereço da receita" opcional erro={erro} className="min-w-0 flex-1">
        <Entrada
          type="url"
          inputMode="url"
          autoComplete="off"
          value={endereco}
          onChange={(evento) => setEndereco(evento.target.value)}
          placeholder="https://www.tudogostoso.com.br/receita/..."
          invalido={Boolean(erro)}
        />
      </Campo>
      <Botao
        type="submit"
        variante="terciario"
        icone={<DownloadSimple size={18} weight="bold" />}
        carregando={trazendo}
        rotuloCarregando="Trazendo…"
      >
        Trazer receita
      </Botao>
    </form>
  );
}

export function FormularioDaReceita({
  rascunho,
  aoMudar,
  aoConferir,
  conferindo,
}: {
  rascunho: Rascunho;
  aoMudar: (parcial: Partial<Rascunho>) => void;
  aoConferir: () => void;
  conferindo: boolean;
}) {
  const [aviso, setAviso] = useState<string | null>(null);
  const [erros, setErros] = useState<{ nome?: string; linhas?: string }>({});

  const conferir = (evento: FormEvent) => {
    evento.preventDefault();
    const novos = {
      ...(rascunho.nome.trim() ? {} : { nome: "Escreva o nome do prato." }),
      ...(rascunho.linhas.trim() ? {} : { linhas: "Escreva pelo menos um ingrediente, um por linha." }),
    };
    setErros(novos);
    if (Object.keys(novos).length === 0) aoConferir();
  };

  return (
    <Card aria-labelledby="titulo-do-prato">
      <TituloSecao
        id="titulo-do-prato"
        titulo="Qual prato?"
        apoio="Cole o endereço de uma receita da internet, ou escreva do jeito que a senhora faz."
      />
      <TrazerDaInternet
        aoTrazer={(novo, texto) => {
          aoMudar(novo);
          setAviso(texto);
          setErros({});
        }}
      />
      {aviso ? (
        <p role="status" className="mt-2 text-sm text-texto">
          {aviso}
        </p>
      ) : null}

      <form noValidate onSubmit={conferir} className="mt-5 space-y-4 border-t border-borda pt-5">
        <Campo rotulo="Nome do prato" erro={erros.nome} obrigatorio>
          <Entrada
            value={rascunho.nome}
            onChange={(evento) => aoMudar({ nome: evento.target.value })}
            placeholder="Bolo de cenoura"
            autoComplete="off"
            invalido={Boolean(erros.nome)}
          />
        </Campo>
        <Campo
          rotulo="Ingredientes, um por linha"
          dica="Do jeito que as receitas escrevem: meia xícara, 2 latas, sal a gosto."
          erro={erros.linhas}
          obrigatorio
        >
          <AreaDeTexto
            value={rascunho.linhas}
            onChange={(evento) => aoMudar({ linhas: evento.target.value })}
            placeholder={EXEMPLO_DE_INGREDIENTES}
            minLinhas={5}
            invalido={Boolean(erros.linhas)}
          />
        </Campo>
        <Campo
          id={ID_DO_PREPARO}
          rotulo="Como a senhora faz, passo a passo"
          dica="É daqui que eu sei se precisa de forno, batedeira ou panela de pressão."
          opcional
        >
          <AreaDeTexto
            value={rascunho.preparo}
            onChange={(evento) => aoMudar({ preparo: evento.target.value })}
            placeholder={"Misture tudo.\nLeve ao forno por 40 minutos."}
            minLinhas={3}
          />
        </Campo>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id={ID_DO_RENDIMENTO} rotulo="Rende quantas porções" dica="Do tamanho que a senhora vai vender.">
            <EntradaNumero
              valor={rascunho.rende}
              aoMudar={(rende) => aoMudar({ rende })}
              casas={0}
              min={1}
              max={500}
              unidade="porções"
            />
          </Campo>
          <Campo
            id={ID_DO_TEMPO}
            rotulo="Quanto tempo fica no fogo"
            dica="Fogo, forno ou aparelho ligado, somando os passos. Se não souber, deixe em branco."
            opcional
          >
            <EntradaNumero
              valor={rascunho.tempo}
              aoMudar={(tempo) => aoMudar({ tempo })}
              casas={0}
              min={1}
              max={1440}
              unidade="minutos"
            />
          </Campo>
        </div>
        <Botao type="submit" carregando={conferindo} rotuloCarregando="Conferindo…" iconeDepois={<ArrowRight size={18} weight="bold" />}>
          Conferir se dá pra fazer
        </Botao>
      </form>
    </Card>
  );
}
