"use client";

/**
 * A guarda antes do "Vou cobrar": o preço já está na tela, mas o aceite pede a
 * cozinha confirmada. Aqui fica o que falta, item por item (a frase da API), e,
 * quando é o que toda cozinha tem, a pergunta, uma só, com o "Sim, tenho tudo
 * isso" e o "Não tenho" de cada item. Depois de responder, a conferência roda
 * de novo, e o "Vou cobrar" libera (ou o prato mostra por que não dá).
 */

import { CheckCircle, SealQuestion } from "@phosphor-icons/react/dist/ssr";
import { useId, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Card } from "@/componentes/compartilhados/Card";
import { ErroDoMotor } from "@/lib/api/base";
import { perfil } from "@/lib/api/perfil";
import type { Avaliacao } from "@/lib/api/preco";
import type { ItemAConfirmar } from "@/lib/api/receitas";
import { useSincronizacao } from "@/lib/dados/sincronizacao";
import { textoParaEla } from "@/lib/formato";

type Envio = { ocupado: string | null; erro: string | null };

export function ConfirmarACozinhaNoPreco({
  avaliacao,
  idDoMotivo,
  aoMudar,
}: {
  avaliacao: Avaliacao;
  /** O id do "falta" escrito aqui: os botões de cobrar apontam para ele. */
  idDoMotivo: string;
  /** Ela respondeu: a tela confere de novo. */
  aoMudar: () => void;
}) {
  const id = useId();
  const [envio, setEnvio] = useState<Envio>({ ocupado: null, erro: null });
  const { avisar } = useSincronizacao();
  const confirmacao = avaliacao.confirmar_a_cozinha;

  const enviar = async (qual: string, pedido: () => Promise<unknown>) => {
    setEnvio({ ocupado: qual, erro: null });
    try {
      await pedido();
      setEnvio({ ocupado: null, erro: null });
      avisar(["perfil", "receitas"]);
      aoMudar();
    } catch (causa) {
      const mensagem = causa instanceof ErroDoMotor ? (causa.pergunta ?? causa.message) : null;
      setEnvio({ ocupado: null, erro: textoParaEla(mensagem, "Não consegui anotar agora. Tente de novo.") });
    }
  };

  const confirmar = () => {
    if (!confirmacao) return;
    // Pela receita que a conferência guardou: grava o que ela usa do suposto.
    const pedido = avaliacao.receita_id
      ? { receita: avaliacao.receita_id }
      : { itens: confirmacao.itens.map(({ tipo, id: item }) => ({ tipo, id: item })) };
    void enviar("tudo", () => perfil.confirmarSupostos(pedido));
  };

  const naoTenho = (item: ItemAConfirmar) =>
    void enviar(item.id, () => perfil.definirPosse(item.tipo === "tecnica" ? "tecnicas" : "equipamentos", item.id, "nao_tem"));

  return (
    <Card aria-labelledby={`titulo${id}`} className="border-atencao/30">
      <h2 id={`titulo${id}`} className="flex items-start gap-2 text-lg font-bold text-tinta">
        <SealQuestion size={26} weight="fill" aria-hidden="true" className="mt-px shrink-0 text-atencao" />
        <span>Antes de cobrar, falta confirmar</span>
      </h2>
      <div id={idDoMotivo} className="mt-2 text-sm text-texto">
        <p>Para a senhora cobrar este preço, falta:</p>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          {avaliacao.falta_para_aceitar.map((falta) => (
            <li key={falta} className="[overflow-wrap:anywhere]">
              {falta}
            </li>
          ))}
        </ul>
      </div>
      {confirmacao ? (
        <div className="mt-4 rounded-md border border-atencao/25 bg-atencao/10 p-3">
          <p id={`pergunta${id}`} className="text-base font-semibold text-tinta">
            {confirmacao.pergunta}
          </p>
          <ul className="mt-3 space-y-2">
            {confirmacao.itens.map((item) => (
              <li key={`${item.tipo}-${item.id}`} className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-base text-tinta">{item.nome}</span>
                <Botao
                  variante="terciario"
                  tamanho="sm"
                  carregando={envio.ocupado === item.id}
                  rotuloCarregando="Anotando…"
                  disabled={envio.ocupado !== null && envio.ocupado !== item.id}
                  aria-label={`${item.tipo === "tecnica" ? "Não faço" : "Não tenho"}: ${item.nome}`}
                  onClick={() => naoTenho(item)}
                >
                  {item.tipo === "tecnica" ? "Não faço" : "Não tenho"}
                </Botao>
              </li>
            ))}
          </ul>
          <Botao
            className="mt-3"
            icone={<CheckCircle size={20} weight="bold" />}
            carregando={envio.ocupado === "tudo"}
            rotuloCarregando="Anotando…"
            disabled={envio.ocupado !== null && envio.ocupado !== "tudo"}
            aria-describedby={`pergunta${id}`}
            onClick={confirmar}
          >
            Sim, tenho tudo isso
          </Botao>
        </div>
      ) : null}
      {envio.erro ? (
        <p role="alert" className="mt-2 text-sm font-medium text-perigo">
          {envio.erro}
        </p>
      ) : null}
    </Card>
  );
}
