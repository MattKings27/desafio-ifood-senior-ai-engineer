/**
 * A cozinha com o perfil do contrato: o seletor Tenho / Não tenho / Não sei,
 * cada item gravando 300 ms depois do último toque e mostrando o que mudou nas
 * receitas, "não sei" como "não sei", os limites da rotina e os filtros na URL.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const acoes = vi.hoisted(() => ({ definirPosse: vi.fn(), definirRestricao: vi.fn(), confirmarSupostos: vi.fn() }));
vi.mock("@/lib/acoes/cozinha", () => acoes);
vi.mock("next/navigation", async () => (await import("@/teste/navegacao")).moduloDeNavegacao);

import { ProvedorDeToasts } from "@/componentes/compartilhados/Toast";
import type {
  ConfirmacaoDaCozinha,
  ItemDaCozinha as Item,
  PerfilDaCozinha,
  RespostaDaCozinha,
  RespostaDePosse,
  Restricao,
} from "@/lib/api/perfil";
import { contrato } from "@/teste/fixturas";
import { irPara } from "@/teste/navegacao";

import { ItemDaCozinha, MiniaturaDoItem, NotaDoImpacto } from "./ItemDaCozinha";
import { LimitesDaRotina, valorNaTela } from "./LimitesDaRotina";
import { OPCOES_DE_POSSE, SeletorDePosse, respostaDoItem } from "./SeletorDePosse";
import { TelaDaCozinha } from "./TelaDaCozinha";
import { TodaCozinha } from "./TodaCozinha";
import { useGravacaoAdiada } from "./useGravacaoAdiada";

const PERFIL = contrato<PerfilDaCozinha>("perfil.json");
const ESCRITA = contrato<{ resposta: RespostaDaCozinha; resposta_restricao: RespostaDaCozinha }>("perfil-escrita.json");
const achar = (id: string) => [...PERFIL.equipamentos, ...PERFIL.tecnicas].find((i) => i.id === id) as Item;
const deu = <T,>(dados: T) => ({ ok: true as const, dados });

function comAvisos(elemento: React.ReactElement) {
  return render(<ProvedorDeToasts>{elemento}</ProvedorDeToasts>);
}

function lista(elemento: React.ReactElement) {
  return comAvisos(<ul>{elemento}</ul>);
}

beforeEach(() => {
  irPara("/cozinha");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("SeletorDePosse", () => {
  function Controlado({ tipo }: { tipo: "equipamento" | "tecnica" }) {
    const [valor, setValor] = useState<RespostaDePosse | null>(null);
    return <SeletorDePosse tipo={tipo} legenda="Forno" valor={valor} aoMudar={setValor} />;
  }

  it("Tenho / Não tenho / Não sei; nada marcado enquanto ela não respondeu", () => {
    render(<Controlado tipo="equipamento" />);
    const grupo = screen.getByRole("group", { name: "Forno" });
    expect(within(grupo).getAllByRole("radio").map((r) => (r as HTMLInputElement).checked)).toEqual([false, false, false]);
    fireEvent.click(within(grupo).getByRole("radio", { name: "Não tenho" }));
    expect(within(grupo).getByRole("radio", { name: "Não tenho" })).toBeChecked();
  });

  it("para técnica, Faço / Não faço / Não sei; a resposta vem do item", () => {
    render(<Controlado tipo="tecnica" />);
    expect(screen.getAllByRole("radio").map((r) => r.getAttribute("value"))).toEqual(["tem", "nao_tem", "nao_sei"]);
    expect(OPCOES_DE_POSSE.tecnica.map((o) => o.rotulo)).toEqual(["Faço", "Não faço", "Não sei"]);
    expect(respostaDoItem(achar("fogao"))).toBeNull();
    expect(respostaDoItem(achar("batedeira"))).toBe("nao_sei");
  });
});

describe("MiniaturaDoItem", () => {
  it("a foto do Commons pelo proxy, pequena, com o crédito ao passar o mouse e embaixo do nome", () => {
    const forno = achar("forno");
    expect(forno.imagem?.url).toMatch(/^\/motor\/imagens\/[0-9a-f]{32}$/);
    const { container } = lista(<ItemDaCozinha item={forno} tipo="equipamentos" />);
    const foto = screen.getByRole("img", { name: "Foto ilustrativa: Forno" });
    expect(foto).toHaveAttribute("src", forno.imagem?.url);
    expect(foto).toHaveAttribute("loading", "lazy");
    const caixa = container.querySelector("[data-miniatura]");
    expect(caixa).toHaveClass("size-16", "shrink-0", "rounded-md");
    expect(caixa).toHaveAttribute("title", forno.imagem?.credito);
    expect(screen.getByText(forno.imagem?.credito ?? "")).toHaveClass("text-xs");
  });

  it("sem foto livre que mostre o item, fica o ícone no mesmo tamanho, sem crédito", () => {
    const reducao = achar("reducao");
    expect(reducao.imagem).toBeNull();
    const { container } = render(<MiniaturaDoItem item={reducao} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[data-miniatura]")).toHaveClass("size-16");
    expect(container.querySelector("[data-miniatura]")).not.toHaveAttribute("title");
    expect(container.querySelector("svg")?.closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("todo item do contrato tem foto ou o ícone, e a foto é sempre do proxy", () => {
    const itens = [...PERFIL.equipamentos, ...PERFIL.tecnicas];
    const comFoto = itens.filter((i) => i.imagem);
    expect(itens).toHaveLength(63);
    expect(comFoto).toHaveLength(62);
    for (const item of comFoto) {
      expect(item.imagem?.url).toMatch(/^\/motor\/imagens\/[0-9a-f]{32}$/);
      expect(item.imagem?.credito).toMatch(/^Foto: .+, Wikimedia Commons$/);
    }
  });
});

describe("ItemDaCozinha", () => {
  it("o suposto pede confirmação, e a resposta grava 300 ms depois do último toque", async () => {
    acoes.definirPosse.mockResolvedValue(deu(ESCRITA.resposta));
    const aoGravar = vi.fn();
    lista(<ItemDaCozinha item={achar("fogao")} tipo="equipamentos" aoGravar={aoGravar} />);
    expect(screen.getByText("Suposto: confirme")).toBeInTheDocument();
    const grupo = screen.getByRole("group", { name: "Fogão" });
    expect(within(grupo).getByRole("radio", { name: "Tenho" })).not.toBeChecked();

    fireEvent.click(within(grupo).getByRole("radio", { name: "Tenho" }));
    fireEvent.click(within(grupo).getByRole("radio", { name: "Não tenho" }));
    expect(screen.getByText("Salvando…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Salvo")).toBeInTheDocument());
    expect(acoes.definirPosse).toHaveBeenCalledOnce();
    expect(acoes.definirPosse).toHaveBeenCalledWith("equipamentos", "fogao", "nao_tem");
    expect(screen.getByText(ESCRITA.resposta.impacto.texto)).toBeInTheDocument();
    expect(aoGravar).toHaveBeenCalledWith(`Fogão: ${ESCRITA.resposta.impacto.texto}`);
  });

  it("não sei é não sei; a conversa aparece como quem mudou; técnica grava no caminho dela", async () => {
    acoes.definirPosse.mockResolvedValue(deu(ESCRITA.resposta));
    const { unmount } = lista(<ItemDaCozinha item={achar("batedeira")} tipo="equipamentos" />);
    expect(screen.getByText("A senhora disse que não sabe")).toBeInTheDocument();
    expect(screen.queryByText("Ainda não perguntei")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Não sei" })).toBeChecked();
    unmount();

    const { unmount: sair } = lista(<ItemDaCozinha item={achar("liquidificador")} tipo="equipamentos" />);
    expect(screen.getByText(/Atualizado pela conversa, hoje, 10:02/)).toBeInTheDocument();
    sair();

    lista(<ItemDaCozinha item={{ ...achar("air_fryer"), atualizado_por: "conversa", atualizado_texto: null }} tipo="tecnicas" />);
    expect(screen.getByText("Ainda não perguntei")).toBeInTheDocument();
    expect(screen.getByText("Atualizado pela conversa")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Faço" }));
    await waitFor(() => expect(acoes.definirPosse).toHaveBeenCalledWith("tecnicas", "air_fryer", "tem"));
  });

  it("a recusa da API volta a escolha e avisa", async () => {
    acoes.definirPosse.mockResolvedValue({ ok: false, erro: { categoria: "ausente", mensagem: "esse equipamento não está na lista da cozinha" } });
    lista(<ItemDaCozinha item={achar("forno")} tipo="equipamentos" />);
    const grupo = screen.getByRole("group", { name: "Forno" });
    expect(within(grupo).getByRole("radio", { name: "Não tenho" })).toBeChecked();
    fireEvent.click(within(grupo).getByRole("radio", { name: "Tenho" }));
    await waitFor(() => expect(screen.getByText("Não salvou")).toBeInTheDocument());
    expect(screen.getByText("esse equipamento não está na lista da cozinha")).toBeInTheDocument();
    expect(within(grupo).getByRole("radio", { name: "Não tenho" })).toBeChecked();
  });

  it("as receitas que dependem do item abrem e fecham; depois de gravar, com os nomes", async () => {
    acoes.definirPosse.mockResolvedValue(deu(ESCRITA.resposta));
    lista(<ItemDaCozinha item={achar("forno")} tipo="equipamentos" />);
    const botao = screen.getByRole("button", { name: /Muda o que dá para fazer em 1 receita/ });
    fireEvent.click(botao);
    expect(botao).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/receitas que a senhora está avaliando/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver as receitas" })).toHaveAttribute("href", "/receitas");
    fireEvent.click(screen.getByRole("radio", { name: "Não sei" }));
    await waitFor(() => expect(screen.getAllByText("Frango assado").length).toBeGreaterThan(0));
    fireEvent.click(botao);
    expect(botao).toHaveAttribute("aria-expanded", "false");
  });

  it("item que nenhuma receita pede não tem a lista; a nota sem mudança é discreta", () => {
    lista(<ItemDaCozinha item={achar("air_fryer")} tipo="equipamentos" />);
    expect(screen.queryByRole("button", { name: /Muda o que dá para fazer/ })).not.toBeInTheDocument();
    render(<NotaDoImpacto impacto={{ liberadas: [], bloqueadas: [], pendentes: [], texto: "Anotado. Nenhuma receita em avaliação muda com isso." }} />);
    expect(screen.getByText("Anotado. Nenhuma receita em avaliação muda com isso.").parentElement).toHaveClass("bg-secao");
  });
});

describe("LimitesDaRotina", () => {
  const restricoes: Record<string, Restricao> = {
    ...PERFIL.restricoes,
    porcoes_por_fornada: { ...(PERFIL.restricoes.porcoes_por_fornada as Restricao), atualizado_por: "conversa", atualizado_texto: "hoje, 09:12" },
  };

  it("o valor na tela: número, sim ou não, não sei, ou ainda não perguntado", () => {
    const bocas = restricoes.bocas_fogao as Restricao;
    expect(valorNaTela({ ...bocas, valor: 4 })).toBe(4);
    expect(valorNaTela({ ...bocas, valor: null, nao_sei: true })).toBe("nao_sei");
    expect(valorNaTela({ ...bocas, valor: null, nao_sei: false })).toBeNull();
  });

  it("+ grava o número; fora da faixa não vai; apagado não é não sei; Não sei grava null", async () => {
    acoes.definirRestricao.mockResolvedValue(deu(ESCRITA.resposta_restricao));
    const aoGravar = vi.fn();
    comAvisos(<LimitesDaRotina restricoes={restricoes} aoGravar={aoGravar} />);
    const regiao = screen.getByRole("region", { name: "Limites da rotina" });
    const bocas = within(regiao).getByLabelText("Bocas do fogão");
    expect(bocas).toHaveValue("4");
    fireEvent.click(within(regiao).getByRole("button", { name: "Mais: Bocas do fogão" }));
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenCalledWith("bocas_fogao", 5));
    await waitFor(() => expect(aoGravar).toHaveBeenCalledWith(`Bocas do fogão: ${ESCRITA.resposta_restricao.impacto.texto}`));

    fireEvent.change(bocas, { target: { value: "40" } });
    expect(await within(regiao).findByText("Diga um número de 1 a 8 bocas.")).toBeInTheDocument();
    fireEvent.change(bocas, { target: { value: "" } });
    fireEvent.change(bocas, { target: { value: "6" } });
    expect(within(regiao).queryByText("Diga um número de 1 a 8 bocas.")).not.toBeInTheDocument();
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenLastCalledWith("bocas_fogao", 6));

    const linha = bocas.closest("li") as HTMLElement;
    fireEvent.click(within(linha).getByRole("button", { name: "Não sei" }));
    expect(within(linha).getByRole("button", { name: "Não sei" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenLastCalledWith("bocas_fogao", null));
    expect(within(linha).getByText("A senhora disse que não sabe")).toBeInTheDocument();
  });

  it("o tempo por cozinhada é em horas, com vírgula; o + anda meia hora e a faixa sai em horas", async () => {
    acoes.definirRestricao.mockResolvedValue(deu(ESCRITA.resposta_restricao));
    comAvisos(<LimitesDaRotina restricoes={restricoes} />);
    const regiao = screen.getByRole("region", { name: "Limites da rotina" });
    const horas = within(regiao).getByLabelText("Horas cozinhando de uma vez");
    expect(horas).toHaveValue("1,5");
    expect(within(regiao).getByText("Quanto tempo a senhora consegue ficar cozinhando de uma vez, sem se estressar ou cansar?")).toBeInTheDocument();
    expect(within(regiao).getByText("horas")).toBeInTheDocument();
    fireEvent.click(within(regiao).getByRole("button", { name: "Mais: Horas cozinhando de uma vez" }));
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenCalledWith("tempo_max_por_fornada_min", 2));
    fireEvent.change(horas, { target: { value: "2,5" } });
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenLastCalledWith("tempo_max_por_fornada_min", 2.5));
    fireEvent.change(horas, { target: { value: "13" } });
    expect(await within(regiao).findByText("Diga um número de 0,5 a 12 horas.")).toBeInTheDocument();
  });

  it("o gás é Sim / Não / Não sei; quem mudou pela conversa aparece", async () => {
    acoes.definirRestricao.mockResolvedValue(deu(ESCRITA.resposta_restricao));
    comAvisos(<LimitesDaRotina restricoes={restricoes} />);
    const gas = screen.getByRole("group", { name: "Botijão de gás de reserva" });
    expect(within(gas).getByRole("radio", { name: "Não sei" })).toBeChecked();
    fireEvent.click(within(gas).getByRole("radio", { name: "Sim" }));
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenLastCalledWith("tem_gas_sobrando", true));
    fireEvent.click(within(gas).getByRole("radio", { name: "Não" }));
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenLastCalledWith("tem_gas_sobrando", false));
    fireEvent.click(within(gas).getByRole("radio", { name: "Não sei" }));
    await waitFor(() => expect(acoes.definirRestricao).toHaveBeenLastCalledWith("tem_gas_sobrando", null));
    expect(screen.getByText("Atualizado pela conversa, hoje, 09:12")).toBeInTheDocument();
    expect(screen.getAllByText("Ainda não perguntei").length).toBeGreaterThan(0);
  });

  it("um limite novo da API aparece pela pergunta, sem unidade", () => {
    comAvisos(
      <LimitesDaRotina
        restricoes={{
          novo: { valor: true, tipo: "sim_nao", pergunta: "Tem ajudante?", atualizado_por: null, atualizado_texto: null, nao_sei: false },
          outro: { valor: null, tipo: "inteiro", pergunta: "Quantas panelas?", atualizado_por: "conversa", atualizado_texto: null, nao_sei: false },
        }}
      />,
    );
    expect(screen.getByRole("group", { name: "Tem ajudante?" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Sim" })).toBeChecked();
    expect(screen.getAllByText("Quantas panelas?").length).toBeGreaterThan(0);
    expect(screen.getByText("Atualizado pela conversa")).toBeInTheDocument();
  });
});

describe("O que toda cozinha tem", () => {
  const BLOCO = PERFIL.toda_cozinha;
  const CONFIRMACAO = contrato<{ resposta: ConfirmacaoDaCozinha }>("perfil-supostos.json").resposta;

  it("cada item com a foto e o estado dito para ela; o texto e a contagem da API", () => {
    comAvisos(<TodaCozinha bloco={BLOCO} />);
    expect(screen.getByText(BLOCO.texto)).toBeInTheDocument();
    expect(screen.getByText(BLOCO.a_confirmar_texto)).toBeInTheDocument();
    const itens = screen.getAllByRole("listitem");
    expect(itens).toHaveLength(BLOCO.itens.length);
    const fogao = itens.find((li) => li.textContent?.startsWith("Fogão")) as HTMLElement;
    expect(within(fogao).getByRole("img", { name: "Foto ilustrativa: Fogão" })).toHaveAttribute("src", expect.stringMatching(/^\/motor\/imagens\//));
    expect(within(fogao).getByText("Suposto: confirme")).toBeInTheDocument();
    expect(within(fogao).getByRole("button", { name: "Não tenho: Fogão" })).toBeInTheDocument();
  });

  it("Tenho tudo isso confirma de uma vez, e o aviso diz o que ficou anotado", async () => {
    acoes.confirmarSupostos.mockResolvedValue(deu(CONFIRMACAO));
    comAvisos(<TodaCozinha bloco={BLOCO} />);
    fireEvent.click(screen.getByRole("button", { name: "Tenho tudo isso" }));
    await waitFor(() => expect(acoes.confirmarSupostos).toHaveBeenCalledWith({}));
    expect(await screen.findByText(CONFIRMACAO.texto)).toBeInTheDocument();
  });

  it("o Não tenho (ou Não faço) de um item grava só ele, pelo perfil", async () => {
    acoes.definirPosse.mockResolvedValue(deu(ESCRITA.resposta));
    comAvisos(<TodaCozinha bloco={BLOCO} />);
    fireEvent.click(screen.getByRole("button", { name: "Não tenho: Fogão" }));
    await waitFor(() => expect(acoes.definirPosse).toHaveBeenCalledWith("equipamentos", "fogao", "nao_tem"));
    fireEvent.click(screen.getByRole("button", { name: "Não faço: Refogar" }));
    await waitFor(() => expect(acoes.definirPosse).toHaveBeenCalledWith("tecnicas", "refogar", "nao_tem"));
  });

  it("com tudo respondido, o cartão fica calmo, com os itens guardados", () => {
    const confirmado = {
      ...BLOCO,
      tudo_confirmado: true,
      a_confirmar: 0,
      texto: "A senhora já me disse de tudo isso.",
      itens: BLOCO.itens.map((i) => ({ ...i, status: "confirmado" as const, status_texto: "a senhora tem" })),
    };
    comAvisos(<TodaCozinha bloco={confirmado} />);
    expect(screen.getByText("A senhora já me disse de tudo isso.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tenho tudo isso" })).not.toBeInTheDocument();
    expect(screen.getByText("Ver os itens")).toBeInTheDocument();
  });
});

describe("TelaDaCozinha", () => {
  const nomesVisiveis = () => screen.queryAllByRole("group").map((g) => g.querySelector("legend")?.textContent);

  it("o progresso com os textos da API, e as duas listas por categoria", () => {
    comAvisos(<TelaDaCozinha perfil={PERFIL} />);
    expect(screen.getByRole("heading", { level: 1, name: "Cozinha" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "O que toda cozinha tem" })).toBeInTheDocument();
    expect(screen.getByText(PERFIL.progresso_texto)).toBeInTheDocument();
    expect(screen.getByText(PERFIL.resumo)).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Respondidos pela senhora" })).toHaveAttribute("aria-valuetext", PERFIL.progresso_texto);
    expect(screen.getByRole("region", { name: "Equipamentos" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Técnicas" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Cocção" })).toBeInTheDocument();
    expect(screen.getByText("63 itens na cozinha")).toBeInTheDocument();
  });

  it("a busca e a situação mudam a URL e as listas; sem nada, o vazio limpa", () => {
    comAvisos(<TelaDaCozinha perfil={PERFIL} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar equipamento ou técnica" }), { target: { value: "forn" } });
    expect(window.location.search).toBe("?q=forn");
    expect(nomesVisiveis()).toContain("Forno");
    expect(nomesVisiveis()).not.toContain("Fogão");
    expect(screen.queryByRole("region", { name: "Técnicas" })).not.toBeInTheDocument();
    expect(screen.getByText("2 encontrados")).toBeInTheDocument();

    const situacao = screen.getByRole("group", { name: "Situação" });
    fireEvent.click(within(situacao).getByRole("checkbox", { name: /Suposto/ }));
    expect(screen.getByText("Nada com esses filtros")).toBeInTheDocument();
    const ativos = screen.getByRole("list", { name: "Filtros ativos" });
    fireEvent.click(within(ativos).getByRole("button", { name: "Suposto: tirar este filtro" }));
    fireEvent.click(within(screen.getByRole("list", { name: "Filtros ativos" })).getByRole("button", { name: "Busca: forn: tirar este filtro" }));
    expect(window.location.search).toBe("");

    fireEvent.click(within(situacao).getByRole("checkbox", { name: /Não sei/ }));
    expect(nomesVisiveis().filter((n) => n !== "Situação" && n !== "Botijão de gás de reserva")).toEqual(["Batedeira"]);
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar equipamento ou técnica" }), { target: { value: "xyz" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Limpar filtros" }).at(-1) as HTMLElement);
    expect(window.location.search).toBe("");
  });

  it("depois de gravar, a região viva diz o que mudou", async () => {
    acoes.definirPosse.mockResolvedValue(deu(ESCRITA.resposta));
    comAvisos(<TelaDaCozinha perfil={PERFIL} />);
    fireEvent.click(within(screen.getByRole("group", { name: "Air fryer" })).getByRole("radio", { name: "Tenho" }));
    await waitFor(() =>
      expect(screen.getAllByRole("status").some((s) => s.textContent === `Air fryer: ${ESCRITA.resposta.impacto.texto}`)).toBe(true),
    );
  });
});

describe("useGravacaoAdiada", () => {
  function Campo({ doServidor, gravar }: { doServidor: number; gravar: (v: number) => Promise<{ ok: true; dados: null }> }) {
    const { valor, mudar, estado, tentarDeNovo } = useGravacaoAdiada(doServidor, gravar);
    return (
      <div>
        <span data-testid="valor">{valor}</span>
        <span data-testid="estado">{estado}</span>
        <button type="button" onClick={() => mudar(valor + 1)}>
          mais
        </button>
        <button type="button" onClick={tentarDeNovo}>
          de novo
        </button>
      </div>
    );
  }

  it("acompanha a página quando nada espera, e grava o que esperava ao sair", async () => {
    const gravar = vi.fn(async () => ({ ok: true as const, dados: null }));
    const { rerender, unmount } = comAvisos(<Campo doServidor={1} gravar={gravar} />);
    rerender(
      <ProvedorDeToasts>
        <Campo doServidor={7} gravar={gravar} />
      </ProvedorDeToasts>,
    );
    expect(screen.getByTestId("valor")).toHaveTextContent("7");
    fireEvent.click(screen.getByRole("button", { name: "mais" }));
    expect(screen.getByTestId("estado")).toHaveTextContent("esperando");
    unmount();
    expect(gravar).toHaveBeenCalledWith(8);
  });

  it("tentar de novo grava o valor de agora; a ação que lança vira falha de rede", async () => {
    const gravar = vi.fn(async () => {
      throw new Error("fora do ar");
    });
    comAvisos(<Campo doServidor={2} gravar={gravar as never} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "de novo" }));
    });
    await waitFor(() => expect(screen.getByTestId("estado")).toHaveTextContent("erro"));
    expect(gravar).toHaveBeenCalledWith(2);
    expect(screen.getByText(/Não consegui falar com o sistema/)).toBeInTheDocument();
  });

  it("sem o aviso, a recusa fica em erro para a tela escrever perto da pergunta, até a próxima escolha", async () => {
    const gravar = vi.fn(async () => ({ ok: false as const, erro: { categoria: "uso" as const, mensagem: "Esse item não está na lista." } }));
    function PerguntaCalada() {
      const { mudar, estado, erro } = useGravacaoAdiada(0, gravar, { avisarErro: false, espera: 0 });
      return (
        <div>
          <span data-testid="estado">{estado}</span>
          {erro ? <p role="alert">{erro.mensagem}</p> : null}
          <button type="button" onClick={() => mudar(1)}>
            mais
          </button>
        </div>
      );
    }
    comAvisos(<PerguntaCalada />);
    fireEvent.click(screen.getByRole("button", { name: "mais" }));
    await waitFor(() => expect(screen.getByTestId("estado")).toHaveTextContent("erro"));
    expect(screen.getAllByText("Esse item não está na lista.")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "mais" }));
    expect(screen.queryByText("Esse item não está na lista.")).not.toBeInTheDocument();
  });
});
