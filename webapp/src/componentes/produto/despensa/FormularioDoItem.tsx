"use client";

/**
 * Acrescentar um ingrediente, ou corrigir um que já está na despensa, numa Folha.
 *
 * Acrescentar: nome, categoria (ou deixar o agente escolher pelo nome),
 * como ela mede (kg, g, L, ml, unidade, ou a embalagem com o peso escrito),
 * quanto tem, de onde veio ("Já tinha" não mexe nos R$ 80; "Comprei com os
 * R$ 80" desconta na hora e pede o preço), quanto comprou, quanto pagou e, se
 * comprou, para qual prato. O `id_cliente` nasce quando a folha abre e se
 * repete nas novas tentativas: o mesmo clique nunca anota duas vezes.
 *
 * Corrigir: o nome fica só para leitura (para trocar o nome, tire o item e
 * acrescente de novo), e só vai para a API o que ela mudou. A unidade nova vale
 * também para o estoque e a quantidade comprada, então trocar a medida pede os
 * dois nela.
 *
 * O que a API recusa volta no campo certo quando dá para saber qual é
 * ("já está na despensa" no nome, a unidade na medida, o saldo no preço); o
 * resto vira aviso.
 */

import clsx from "clsx";
import type { FormEvent } from "react";
import { useId, useState } from "react";

import { Botao } from "@/componentes/compartilhados/Botao";
import { Campo, Entrada, EntradaNumero, Selecao } from "@/componentes/compartilhados/Campos";
import { Folha } from "@/componentes/compartilhados/Folha";
import { Segmentado } from "@/componentes/compartilhados/Segmentado";
import { useToast } from "@/componentes/compartilhados/Toast";
import type { ErroDaAcao } from "@/lib/acoes/base";
import { adicionarItem, corrigirItem } from "@/lib/acoes/despensa";
import type {
  CategoriaParaEscolher,
  CorrecaoDoItem,
  DetalheDoItem,
  NovoItem,
  OrcamentoDaDespensa,
} from "@/lib/api/despensa";
import { useAcao } from "@/lib/dados/useAcao";
import { novoIdCliente } from "@/lib/dados/id";
import { formatarNumero, lerNumeroBR } from "@/lib/formato";

import { useAvisoComDesfazer } from "./avisos";

/* -------------------------------------------------------------------------- */
/* A medida: as unidades que a conta da API lê                                  */
/* -------------------------------------------------------------------------- */

export type Medida = "kg" | "g" | "L" | "ml" | "un" | "embalagem";

export const MEDIDAS: readonly { valor: Medida; rotulo: string; sufixo: string }[] = [
  { valor: "kg", rotulo: "Quilo (kg)", sufixo: "kg" },
  { valor: "g", rotulo: "Grama (g)", sufixo: "g" },
  { valor: "L", rotulo: "Litro (L)", sufixo: "L" },
  { valor: "ml", rotulo: "Mililitro (ml)", sufixo: "ml" },
  { valor: "un", rotulo: "Unidade, sem o peso escrito", sufixo: "un" },
  { valor: "embalagem", rotulo: "Embalagem com o peso escrito", sufixo: "emb." },
];

const UNIDADES_DO_CONTEUDO = ["g", "kg", "ml", "L"] as const;

export type MedidaLida = { medida: Medida; conteudo: number | null; unidadeDoConteudo: string };

/** A unidade como a API guarda ("un 200g", "balde 2kg", "kg") lida para o formulário. */
export function medidaDoRotulo(rotulo: string): MedidaLida {
  const limpo = rotulo.trim();
  const simples = MEDIDAS.find((m) => m.valor !== "embalagem" && m.valor.toLowerCase() === limpo.toLowerCase());
  if (simples) return { medida: simples.valor, conteudo: null, unidadeDoConteudo: "g" };
  const achado = /(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b/i.exec(limpo);
  if (achado) {
    const simbolo = (achado[2] ?? "g").toLowerCase();
    return { medida: "embalagem", conteudo: lerNumeroBR(achado[1] ?? ""), unidadeDoConteudo: simbolo === "l" ? "L" : simbolo };
  }
  return { medida: "un", conteudo: null, unidadeDoConteudo: "g" };
}

/** A unidade que vai para a API: a medida, ou a embalagem com o peso ("un 200g"). */
export function unidadeDaMedida({ medida, conteudo, unidadeDoConteudo }: MedidaLida): string {
  if (medida !== "embalagem") return medida;
  return `un ${formatarNumero(conteudo ?? 0, 3)}${unidadeDoConteudo}`;
}

/* -------------------------------------------------------------------------- */
/* O erro da API no campo certo                                                 */
/* -------------------------------------------------------------------------- */

export type CampoDoFormulario = "nome" | "medida" | "conteudo" | "estoque" | "quantidade" | "preco" | "formulario";

export function campoDoErro(erro: ErroDaAcao): CampoDoFormulario | null {
  const texto = erro.mensagem.toLocaleLowerCase("pt-BR");
  if (erro.categoria === "regra" || /pagou|preço|orçamento/.test(texto)) return "preco";
  if (/nome|já está na despensa/.test(texto)) return "nome";
  if (/unidade|embalagem/.test(texto)) return "medida";
  if (/quantidade|comprou/.test(texto)) return "quantidade";
  if (/estoque/.test(texto)) return "estoque";
  return null;
}

type Erros = Partial<Record<CampoDoFormulario, string>>;

/* -------------------------------------------------------------------------- */
/* O formulário                                                                 */
/* -------------------------------------------------------------------------- */

export type PedidoDoFormulario =
  | { modo: "novo"; origem: "ja_tinha" | "orcamento" }
  | { modo: "editar"; item: DetalheDoItem };

export function FormularioDoItem({
  pedido,
  aoFechar,
  categorias,
  orcamento,
}: {
  /** `null` com a folha fechada. */
  pedido: PedidoDoFormulario | null;
  aoFechar: () => void;
  categorias: readonly CategoriaParaEscolher[];
  orcamento?: OrcamentoDaDespensa | null;
}) {
  const idDoFormulario = useId();
  const avisar = useAvisoComDesfazer();
  const aoConcluir = (dados: { texto: string; evento: string | null }) => {
    avisar(dados.texto, dados.evento);
    aoFechar();
  };
  const novo = useAcao(adicionarItem, { avisarErro: false, aoConcluir });
  const correcao = useAcao(corrigirItem, { avisarErro: false, aoConcluir });

  // Cada abertura começa do zero: a chave troca quando a folha abre de novo.
  const [aberturas, setAberturas] = useState(0);
  const [estavaAberta, setEstavaAberta] = useState(pedido !== null);
  if ((pedido !== null) !== estavaAberta) {
    setEstavaAberta(pedido !== null);
    if (pedido !== null) setAberturas((n) => n + 1);
  }

  const editando = pedido?.modo === "editar";
  const titulo = editando ? `Corrigir ${pedido.item.nome}` : pedido?.origem === "orcamento" ? "Registrar compra" : "Adicionar ingrediente";

  return (
    <Folha
      aberto={pedido !== null}
      aoFechar={aoFechar}
      titulo={titulo}
      descricao={
        editando
          ? "Mude só o que estiver diferente. O que ficar em branco continua como está."
          : "Anote o que a senhora tem. As contas saem daqui."
      }
      rodape={
        <>
          <Botao variante="terciario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao
            type="submit"
            form={idDoFormulario}
            carregando={novo.pendente || correcao.pendente}
            rotuloCarregando="Anotando…"
          >
            {editando ? "Salvar" : "Anotar na despensa"}
          </Botao>
        </>
      }
    >
      {pedido ? (
        <CamposDoItem
          key={aberturas}
          id={idDoFormulario}
          pedido={pedido}
          categorias={categorias}
          orcamento={orcamento ?? null}
          adicionar={novo.executar}
          corrigir={correcao.executar}
        />
      ) : null}
    </Folha>
  );
}

function CamposDoItem({
  id,
  pedido,
  categorias,
  orcamento,
  adicionar,
  corrigir,
}: {
  id: string;
  pedido: PedidoDoFormulario;
  categorias: readonly CategoriaParaEscolher[];
  orcamento: OrcamentoDaDespensa | null;
  adicionar: typeof adicionarItem;
  corrigir: typeof corrigirItem;
}) {
  const toast = useToast();
  const item = pedido.modo === "editar" ? pedido.item : null;
  const inicial = item ? medidaDoRotulo(item.unidade_compra_rotulo) : { medida: "kg" as Medida, conteudo: null, unidadeDoConteudo: "g" };

  const [nome, setNome] = useState(item?.nome ?? "");
  const [categoria, setCategoria] = useState(item?.categoria ?? "");
  const [medida, setMedida] = useState<Medida>(inicial.medida);
  const [conteudo, setConteudo] = useState<number | null>(inicial.conteudo);
  const [unidadeDoConteudo, setUnidadeDoConteudo] = useState(inicial.unidadeDoConteudo);
  const [estoque, setEstoque] = useState<number | null>(null);
  const [origem, setOrigem] = useState<"ja_tinha" | "orcamento">(pedido.modo === "novo" ? pedido.origem : "ja_tinha");
  const [quantidade, setQuantidade] = useState<number | null>(null);
  const [preco, setPreco] = useState<number | null>(null);
  const [prato, setPrato] = useState("");
  const [erros, setErros] = useState<Erros>({});
  const [idCliente] = useState(novoIdCliente);

  const sufixo = MEDIDAS.find((m) => m.valor === medida)?.sufixo ?? "";
  // A medida de agora, lida do rótulo da API: sem mudança, o rótulo dela vai
  // de volta como estava ("balde 2kg" continua "balde 2kg").
  const mesmaMedida =
    item !== null &&
    inicial.medida === medida &&
    (medida !== "embalagem" || (inicial.conteudo === conteudo && inicial.unidadeDoConteudo === unidadeDoConteudo));
  const mudouAMedida = item !== null && !mesmaMedida;
  const unidade = item && mesmaMedida ? item.unidade_compra_rotulo : unidadeDaMedida({ medida, conteudo, unidadeDoConteudo });

  const falhou = (erro: ErroDaAcao) => {
    const campo = campoDoErro(erro);
    const texto = erro.pergunta ?? erro.mensagem;
    if (campo) setErros({ [campo]: texto });
    else toast.mostrar({ texto, tom: "erro" });
  };

  const conferir = (): Erros => {
    const achados: Erros = {};
    if (!item && !nome.trim()) achados.nome = "Escreva o nome do ingrediente.";
    if (medida === "embalagem" && (conteudo === null || conteudo <= 0)) {
      achados.conteudo = "Diga quanto vem em cada embalagem, como está no rótulo.";
    }
    if (!item && estoque === null) achados.estoque = "Diga quanto a senhora tem agora. Se acabou, pode pôr 0.";
    if (!item && origem === "orcamento" && (preco === null || preco <= 0)) {
      achados.preco = "Para comprar com os complementos, diga quanto a senhora pagou.";
    }
    if (mudouAMedida && estoque === null) achados.estoque = "Com a medida nova, diga quanto a senhora tem nela.";
    if (mudouAMedida && quantidade === null) achados.quantidade = "Com a medida nova, diga quanto comprou nela.";
    return achados;
  };

  const enviar = async (evento: FormEvent<HTMLFormElement>) => {
    evento.preventDefault();
    const achados = conferir();
    setErros(achados);
    if (Object.keys(achados).length > 0) return;

    if (!item) {
      const pedidoNovo: NovoItem = {
        nome: nome.trim(),
        estoque: estoque ?? 0,
        unidade,
        origem,
        id_cliente: idCliente,
        ...(categoria ? { categoria } : {}),
        ...(quantidade !== null ? { quantidade_comprada: quantidade } : {}),
        ...(preco !== null ? { preco_pago: preco } : {}),
        ...(origem === "orcamento" && prato.trim() ? { receita: prato.trim() } : {}),
      };
      const resultado = await adicionar(pedidoNovo);
      if (!resultado.ok) falhou(resultado.erro);
      return;
    }

    const mudanca: CorrecaoDoItem = {
      ...(categoria && categoria !== item.categoria ? { categoria } : {}),
      ...(estoque !== null ? { estoque } : {}),
      ...(mudouAMedida || estoque !== null || quantidade !== null ? { unidade } : {}),
      ...(quantidade !== null ? { quantidade_comprada: quantidade } : {}),
      ...(preco !== null ? { preco_pago: preco } : {}),
    };
    if (Object.keys(mudanca).length === 0) {
      setErros({ formulario: "Nada mudou. Mude o que estiver diferente e salve de novo." });
      return;
    }
    const resultado = await corrigir(item.id, { ...mudanca, id_cliente: idCliente });
    if (!resultado.ok) falhou(resultado.erro);
  };

  const rotuloDaOrigemComprada = orcamento ? `Comprei com os ${orcamento.inicial.texto}` : "Comprei com o orçamento";

  return (
    <form id={id} noValidate onSubmit={(evento) => void enviar(evento)} className="flex flex-col gap-5">
      {erros.formulario ? (
        <p role="alert" className="rounded-sm bg-atencao/10 p-3 text-sm font-semibold text-atencao">
          {erros.formulario}
        </p>
      ) : null}

      <Campo
        rotulo="Nome do ingrediente"
        erro={erros.nome}
        dica={item ? "Para trocar o nome, tire o item e acrescente de novo." : undefined}
      >
        <Entrada
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          readOnly={item !== null}
          autoComplete="off"
          maxLength={80}
          className={clsx(item && "bg-secao text-apagado")}
        />
      </Campo>

      <Campo rotulo="Categoria" dica={item ? undefined : "Sem escolher, o agente põe pela palavra do nome."}>
        <Selecao value={categoria} onChange={(e) => setCategoria(e.target.value)}>
          {item ? null : <option value="">O agente escolhe</option>}
          {categorias.map((c) => (
            <option key={c.id} value={c.id}>
              {c.rotulo}
            </option>
          ))}
        </Selecao>
      </Campo>

      <Campo rotulo="Como a senhora mede" erro={erros.medida}>
        <Selecao value={medida} onChange={(e) => setMedida(e.target.value as Medida)} opcoes={MEDIDAS} />
      </Campo>

      {medida === "embalagem" ? (
        <Campo rotulo="Quanto vem em cada embalagem" erro={erros.conteudo}>
          <div className="flex gap-2">
            <EntradaNumero valor={conteudo} aoMudar={setConteudo} casas={3} min={0} className="min-w-0" />
            <Selecao
              id={`${id}-unidade-da-embalagem`}
              aria-label="Unidade do que vem na embalagem"
              value={unidadeDoConteudo}
              onChange={(e) => setUnidadeDoConteudo(e.target.value)}
              opcoes={UNIDADES_DO_CONTEUDO.map((u) => ({ valor: u, rotulo: u }))}
              className="w-24"
            />
          </div>
        </Campo>
      ) : null}

      <Campo
        rotulo={medida === "embalagem" ? "Quantas embalagens tem agora" : "Quanto tem agora"}
        erro={erros.estoque}
        dica={item ? `Hoje: ${item.estoque_texto}. Em branco, continua assim.` : undefined}
      >
        <EntradaNumero valor={estoque} aoMudar={setEstoque} casas={3} min={0} unidade={sufixo} />
      </Campo>

      {item ? (
        <p className="text-sm text-apagado">
          De onde veio: <span className="font-semibold text-texto">{item.origem_rotulo}</span>
        </p>
      ) : (
        <Segmentado
          legenda="De onde veio"
          opcoes={[
            { valor: "ja_tinha", rotulo: "Já tinha" },
            { valor: "orcamento", rotulo: rotuloDaOrigemComprada },
          ]}
          valor={origem}
          aoMudar={setOrigem}
          orientacao="vertical"
        />
      )}
      {!item && origem === "orcamento" && orcamento ? (
        <p className="-mt-3 text-sm text-apagado">Restam {orcamento.restante.texto} para complementos.</p>
      ) : null}

      <Campo
        rotulo={medida === "embalagem" ? "Quantas embalagens comprou" : "Quanto comprou"}
        opcional
        erro={erros.quantidade}
        dica={item ? `Hoje: ${item.comprado_texto}.` : "Em branco, conto o que a senhora tem agora."}
      >
        <EntradaNumero valor={quantidade} aoMudar={setQuantidade} casas={3} min={0} unidade={sufixo} />
      </Campo>

      <Campo
        rotulo="Quanto pagou"
        opcional={item !== null || origem === "ja_tinha"}
        erro={erros.preco}
        dica={
          item
            ? `Hoje: ${item.pago?.texto ?? "sem o preço"}.`
            : origem === "ja_tinha"
              ? "Sem o preço, eu pergunto depois."
              : undefined
        }
      >
        <EntradaNumero valor={preco} aoMudar={setPreco} casas={2} min={0} prefixo="R$" />
      </Campo>

      {!item && origem === "orcamento" ? (
        <Campo rotulo="Para qual prato comprou" opcional>
          <Entrada value={prato} onChange={(e) => setPrato(e.target.value)} autoComplete="off" maxLength={200} />
        </Campo>
      ) : null}
    </form>
  );
}
