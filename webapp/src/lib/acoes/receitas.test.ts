/**
 * As Server Actions da tela de receitas: o que se confere antes de ir à API,
 * o pedido que chega à API, o pouco que volta para a tela, e quando a rota é
 * refeita (as notas, que se salvam sozinhas, não refazem).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/cache", () => ({ refresh: () => refresh() }));

import { api } from "@/lib/api";
import { ErroDoMotor } from "@/lib/api/base";
import { precoDeHoje } from "@/lib/api/preco";
import type { DetalheDaReceita, RespostaDaAvaliacao, RespostaDasNotas } from "@/lib/api/receitas";
import { contrato } from "@/teste/fixturas";

import {
  anotarReceita,
  avaliarReceita,
  informarPrecoDoQueFalta,
  responderLimiteDaCozinha,
  responderSobreACozinha,
  responderSobreAReceita,
  trazerReceita,
} from "./receitas";

const RECEITA = contrato<DetalheDaReceita>("receita.json");
const IMPACTO = { liberadas: [], bloqueadas: [], pendentes: [], texto: "Com forno, Pudim passa a dar." };

afterEach(() => {
  vi.restoreAllMocks();
  refresh.mockClear();
});

describe("trazer uma receita", () => {
  it("endereço que não é de página é recusado antes de ir à API", async () => {
    const trazer = vi.spyOn(api.receitas, "trazer");
    for (const url of ["", "bolo de fubá", "ftp://site.com/x", "https://semponto"]) {
      await expect(trazerReceita(url)).resolves.toMatchObject({ ok: false, erro: { categoria: "uso" } });
    }
    expect(trazer).not.toHaveBeenCalled();
  });

  it("volta só o que a folha mostra, e refaz a grade", async () => {
    const trazer = vi.spyOn(api.receitas, "trazer").mockResolvedValue({ receita: RECEITA, nova: true });
    await expect(trazerReceita("  https://www.tudogostoso.com.br/receita/1  ")).resolves.toEqual({
      ok: true,
      dados: {
        slug: RECEITA.slug,
        nome: RECEITA.nome,
        rota: RECEITA.rota,
        imagem: RECEITA.imagem,
        site: "TudoGostoso",
        nova: true,
        cozinha: RECEITA.veredito_da_cozinha,
        gosta: true,
      },
    });
    expect(trazer).toHaveBeenCalledWith("https://www.tudogostoso.com.br/receita/1");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("a recusa da página chega como dado, com a pergunta", async () => {
    vi.spyOn(api.receitas, "trazer").mockRejectedValue(new ErroDoMotor("sem receita", "dado", "Tenta outro?"));
    await expect(trazerReceita("https://exemplo.com.br/x")).resolves.toEqual({
      ok: false,
      erro: { categoria: "dado", mensagem: "sem receita", pergunta: "Tenta outro?" },
    });
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("responder o que segura uma receita", () => {
  it("a resposta sobre a receita: vazia é recusada; senão volta para onde ela foi", async () => {
    const responder = vi.spyOn(api.receitas, "responder").mockResolvedValue(RECEITA);
    await expect(responderSobreAReceita("s1", "tempo_cozimento_min", "   ")).resolves.toMatchObject({ ok: false });
    expect(responder).not.toHaveBeenCalled();
    await expect(responderSobreAReceita("s1", "tempo_cozimento_min", " 1 hora e 10 minutos ")).resolves.toEqual({
      ok: true,
      dados: { slug: RECEITA.slug, nome: RECEITA.nome, cozinha: RECEITA.veredito_da_cozinha },
    });
    expect(responder).toHaveBeenCalledWith("s1", { campo: "tempo_cozimento_min", resposta: "1 hora e 10 minutos" });
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("a cozinha: tem, não tem ou não sei, e a frase do que muda", async () => {
    const posse = vi.spyOn(api.perfil, "definirPosse").mockResolvedValue({ item: {} as never, impacto: IMPACTO, perfil: {} as never });
    await expect(responderSobreACozinha("equipamentos", "forno", "tem")).resolves.toEqual({ ok: true, dados: { texto: IMPACTO.texto } });
    expect(posse).toHaveBeenCalledWith("equipamentos", "forno", "tem");
    const limite = vi.spyOn(api.perfil, "definirRestricao").mockResolvedValue({ item: {} as never, impacto: IMPACTO, perfil: {} as never });
    await expect(responderLimiteDaCozinha("bocas_fogao", 4)).resolves.toEqual({ ok: true, dados: { texto: IMPACTO.texto } });
    expect(limite).toHaveBeenCalledWith("bocas_fogao", 4);
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("o preço do que falta: conferido antes, um pedido por ingrediente, as frases juntas", async () => {
    const registrar = vi
      .spyOn(precoDeHoje, "registrarPreco")
      .mockResolvedValueOnce({ texto: "milho verde: R$ 6,00 por 1 lata." } as never)
      .mockResolvedValueOnce({ texto: "creme de leite: R$ 4,50 por 1 caixa." } as never);
    await expect(informarPrecoDoQueFalta([])).resolves.toMatchObject({ ok: false });
    await expect(informarPrecoDoQueFalta([{ ingrediente: "milho", valor: 0, quantidade: 1, unidade: "lata" }])).resolves.toMatchObject({
      ok: false,
      erro: { mensagem: "Diga quanto custa milho." },
    });
    await expect(informarPrecoDoQueFalta([{ ingrediente: "milho", valor: 6, quantidade: 0, unidade: "lata" }])).resolves.toMatchObject({
      ok: false,
    });
    await expect(informarPrecoDoQueFalta([{ ingrediente: "milho", valor: 6, quantidade: 1, unidade: "  " }])).resolves.toMatchObject({
      ok: false,
    });
    expect(registrar).not.toHaveBeenCalled();
    await expect(
      informarPrecoDoQueFalta([
        { ingrediente: "milho verde", valor: 6, quantidade: 1, unidade: " lata " },
        { ingrediente: "creme de leite", valor: 4.5, quantidade: 1, unidade: "caixa" },
      ]),
    ).resolves.toEqual({ ok: true, dados: { texto: "milho verde: R$ 6,00 por 1 lata. creme de leite: R$ 4,50 por 1 caixa." } });
    expect(registrar).toHaveBeenNthCalledWith(1, "milho verde", 6, { quantidade: 1, unidade: "lata" });
    expect(registrar).toHaveBeenNthCalledWith(2, "creme de leite", 4.5, { quantidade: 1, unidade: "caixa" });
  });
});

describe("avaliar e anotar", () => {
  it("avaliar manda só o que mudou e refaz a rota (a pontuação e o ranking mudam)", async () => {
    const resposta = contrato<{ resposta: RespostaDaAvaliacao }>("avaliacao-escrita.json").resposta;
    const avaliar = vi.spyOn(api.receitas, "avaliar").mockResolvedValue(resposta);
    await expect(avaliarReceita("s1", { estrelas: { sabor: 5 } })).resolves.toEqual({ ok: true, dados: resposta });
    expect(avaliar).toHaveBeenCalledWith("s1", { estrelas: { sabor: 5 } });
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("as notas se salvam sem refazer a rota: o texto dela não é trocado no meio", async () => {
    const resposta = contrato<{ resposta: RespostaDasNotas }>("notas-escrita.json").resposta;
    const salvar = vi.spyOn(api.receitas, "salvarNotas").mockResolvedValue(resposta);
    await expect(anotarReceita("s1", "Servir com arroz branco.")).resolves.toEqual({ ok: true, dados: resposta });
    expect(salvar).toHaveBeenCalledWith("s1", "Servir com arroz branco.");
    expect(refresh).not.toHaveBeenCalled();
  });
});
