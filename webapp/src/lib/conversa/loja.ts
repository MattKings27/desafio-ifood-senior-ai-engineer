/**
 * A loja da conversa: uma só, por trás de todas as vistas (a página
 * /conversa, o painel, o selo do Conversar e o título da aba).
 *
 * Guarda o estado da conversa aberta (o redutor puro de `estado.ts`), a lista
 * de conversas, a caixa de texto, o painel aberto e as respostas não lidas, e
 * faz o que o redutor não faz: busca, envia, assina o fluxo do turno, agrupa
 * os pedaços de texto num quadro de animação, avisa as telas do que mudou.
 *
 * Lida com `useSyncExternalStore` (ver `useLoja` no provedor): `ler()` devolve
 * o mesmo objeto até alguma coisa mudar, então cada vista redesenha só quando
 * o pedaço que ela olha muda.
 */

import type {
  AcaoDoCartao,
  ContextoDaConversa,
  EventoDoTurno,
  ListaDeConversas,
  OpcaoSugerida,
  PedidoDeTurno,
  ResumoDaConversa,
} from "@/lib/api/conversa";
import { ErroDoMotor, MENSAGENS } from "@/lib/api/base";
import { novoIdCliente } from "@/lib/dados/id";
import { textoParaEla } from "@/lib/formato";
import type { Assinatura } from "@/lib/sse";

import type { DesfechoDaResposta } from "@/lib/api/conversa";

import type { AcaoDaConversa, EstadoDaConversa, ErroNaTela } from "./estado";
import { ESTADO_INICIAL, reduzirConversa } from "./estado";
import type { Transporte } from "./transporte";
import { ehFimDoTurno } from "./transporte";

/** Como terminou o último turno desta sessão, e qual resposta ele deixou. */
export type DesfechoDoTurnoNaLoja = { chave: string; estado: DesfechoDaResposta };

/** O maior texto que ela pode mandar de uma vez. */
export const LIMITE_DE_CARACTERES = 2_000;

/** Caída há mais que isso: pergunta ao servidor se o turno já terminou. */
export const ESPERA_ANTES_DE_CONSULTAR_MS = 60_000;

/** Silêncio maior que isso num turno (sem nenhum evento): consulta o estado. */
export const SILENCIO_MAXIMO_MS = 5 * 60_000;

/** Fora do ar, a tela pergunta de novo de tempos em tempos, e a faixa some sozinha. */
export const NOVA_VERIFICACAO_MS = 30_000;

export const MOTIVO_FORA_DO_AR =
  "O agente está fora do ar agora. As outras telas continuam funcionando normalmente.";

export const AVISO_DE_TURNO_RODANDO =
  "Ainda estou respondendo a mensagem anterior. Quando eu terminar, a senhora manda esta.";

export type EstadoDaLista = {
  carregamento: "vazia" | "carregando" | "pronta" | "falhou";
  atual: string | null;
  conversas: ResumoDaConversa[];
};

export type EstadoDaCaixa = {
  texto: string;
  contexto: ContextoDaConversa | null;
  /** Muda cada vez que alguém pede o foco na caixa (abrir o painel, preencher). */
  foco: number;
};

export type AvisoDaLoja = { id: number; texto: string; tom: "info" | "erro" };

export type EstadoDaLoja = {
  conversa: EstadoDaConversa;
  lista: EstadoDaLista;
  caixa: EstadoDaCaixa;
  painelAberto: boolean;
  naoLidas: number;
  disponibilidade: {
    disponivel: boolean;
    motivo: string | null;
    /** O modelo que responde (`claude-fable-5-1`), quando o backend diz. */
    modelo: string | null;
    /** Já perguntou ao backend ao menos uma vez. */
    conferida: boolean;
  };
  online: boolean;
  aviso: AvisoDaLoja | null;
  /** O último turno que terminou nesta sessão (para anunciar "Resposta pronta"). */
  ultimoDesfecho: DesfechoDoTurnoNaLoja | null;
};

export type DependenciasDaLoja = {
  transporte: Transporte;
  agora?: () => number;
  /** Agenda o redesenho dos eventos que chegaram (um quadro de animação). */
  agendar?: (tarefa: () => void) => () => void;
  /** A sincronização entre superfícies: `estado.alterado` chega aqui. */
  avisar?: (recursos: readonly string[]) => void;
  novoIdCliente?: () => string;
};

export type OpcoesDoEnvio = {
  contexto?: ContextoDaConversa | null;
  acao?: AcaoDoCartao;
};

export type Loja = {
  ler: () => EstadoDaLoja;
  assinar: (ouvinte: () => void) => () => void;
  /** A primeira vez que uma vista da conversa aparece: carrega a conversa atual e o estado do chat. */
  ativar: () => void;
  abrirConversa: (id?: string | null) => Promise<void>;
  recarregarConversa: () => Promise<void>;
  carregarLista: () => Promise<ListaDeConversas | null>;
  novaConversa: () => Promise<boolean>;
  apagarConversa: (id: string) => Promise<boolean>;
  renomearConversa: (id: string, titulo: string) => Promise<boolean>;
  enviar: (texto: string, opcoes?: OpcoesDoEnvio) => Promise<boolean>;
  /** Manda o que está na caixa, com o contexto do chip, e limpa a caixa. */
  enviarDaCaixa: () => Promise<boolean>;
  /** Uma resposta rápida ou uma sugestão de começo: o texto (e a ação), com o contexto do chip. */
  enviarSugestao: (opcao: OpcaoSugerida) => Promise<boolean>;
  /** Abre outra conversa da lista e a marca como a atual (a que abre da próxima vez). */
  trocarConversa: (id: string) => Promise<void>;
  /** Apaga todas as conversas, uma a uma, pela rota de apagar. */
  apagarTodas: () => Promise<boolean>;
  /** Os dados voltaram à planilha e as conversas saíram no servidor: a loja esquece as dela. */
  esquecerConversas: () => void;
  /** Pergunta ao backend se o agente atende agora (e com que modelo). */
  verificarDisponibilidade: () => Promise<void>;
  reenviar: (idCliente: string) => Promise<void>;
  perguntarDeNovo: (chaveDaResposta: string) => Promise<void>;
  parar: () => Promise<void>;
  definirTexto: (texto: string) => void;
  definirContexto: (contexto: ContextoDaConversa | null) => void;
  preencher: (pedido: { rascunho?: string; contexto?: ContextoDaConversa | null }) => void;
  pedirFoco: () => void;
  definirPainel: (aberto: boolean) => void;
  definirVisivel: (visivel: boolean) => void;
  definirOnline: (online: boolean) => void;
  verificarEmSegundoPlano: () => Promise<void>;
  limparAviso: () => void;
  destruir: () => void;
};

/** Um quadro de animação (com reserva por tempo, que a aba de fundo não roda quadros). */
export function agendarNoQuadro(tarefa: () => void): () => void {
  let pendente = true;
  let quadro: number | null = null;
  let reserva: ReturnType<typeof setTimeout> | null = null;
  const cancelar = () => {
    pendente = false;
    if (quadro !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(quadro);
    if (reserva !== null) clearTimeout(reserva);
  };
  const rodar = () => {
    if (!pendente) return;
    cancelar();
    tarefa();
  };
  if (typeof requestAnimationFrame === "function") quadro = requestAnimationFrame(rodar);
  reserva = setTimeout(rodar, 100);
  return cancelar;
}

/** Qualquer falha como erro para a tela: a frase da API, ou a do caminho. */
export function paraErroNaTela(causa: unknown): ErroNaTela {
  if (causa instanceof ErroDoMotor) return { categoria: causa.categoria, mensagem: causa.message };
  return { categoria: "rede", mensagem: MENSAGENS.rede };
}

function resumosValidos(conversas: unknown): ResumoDaConversa[] {
  if (!Array.isArray(conversas)) return [];
  return conversas.filter(
    (c): c is ResumoDaConversa =>
      typeof c === "object" && c !== null && typeof (c as ResumoDaConversa).id === "string",
  );
}

export function criarLoja(dependencias: DependenciasDaLoja): Loja {
  const { transporte } = dependencias;
  const agora = dependencias.agora ?? Date.now;
  const agendar = dependencias.agendar ?? agendarNoQuadro;
  const gerarId = dependencias.novoIdCliente ?? novoIdCliente;

  let estado: EstadoDaLoja = {
    conversa: ESTADO_INICIAL,
    lista: { carregamento: "vazia", atual: null, conversas: [] },
    caixa: { texto: "", contexto: null, foco: 0 },
    painelAberto: false,
    naoLidas: 0,
    disponibilidade: { disponivel: true, motivo: null, modelo: null, conferida: false },
    online: true,
    aviso: null,
    ultimoDesfecho: null,
  };
  const ouvintes = new Set<() => void>();
  let visivel = false;
  let ativada = false;
  let destruida = false;
  let geracao = 0;
  let numeroDoAviso = 0;
  let verificando = false;

  type Fio = { conversaId: string; turnoId: string; assinatura: Assinatura | null };
  let fio: Fio | null = null;
  let fila: EventoDoTurno[] = [];
  let cancelarDescarga: (() => void) | null = null;
  let vigia: ReturnType<typeof setInterval> | null = null;
  let novaVerificacao: ReturnType<typeof setTimeout> | null = null;

  /* --- o estado ----------------------------------------------------------- */

  const notificar = () => {
    for (const ouvinte of [...ouvintes]) ouvinte();
  };

  const definir = (mudar: (atual: EstadoDaLoja) => EstadoDaLoja) => {
    if (destruida) return;
    const novo = mudar(estado);
    if (novo === estado) return;
    estado = novo;
    notificar();
  };

  const mostrarAviso = (texto: string, tom: AvisoDaLoja["tom"]) => {
    numeroDoAviso += 1;
    const aviso = { id: numeroDoAviso, texto, tom };
    definir((atual) => ({ ...atual, aviso }));
  };

  const despachar = (acao: AcaoDaConversa) => {
    if (destruida) return;
    const antes = estado.conversa;
    const depois = reduzirConversa(antes, acao);
    if (depois !== antes) {
      estado = { ...estado, conversa: depois };
      depoisDeMudar(antes, depois);
      notificar();
    }
    sincronizarFio();
  };

  /** O que acontece quando um turno acaba: não lidas, anúncio, a lista, a resposta gravada. */
  const depoisDeMudar = (antes: EstadoDaConversa, depois: EstadoDaConversa) => {
    const terminou = antes.turno?.id && !depois.turno && antes.id === depois.id;
    if (!terminou) return;
    const ultimo = depois.itens.at(-1);
    if (ultimo?.tipo !== "consultora") return;
    const desfecho: DesfechoDoTurnoNaLoja = { chave: ultimo.chave, estado: ultimo.estado };
    estado = {
      ...estado,
      ultimoDesfecho: desfecho,
      naoLidas: !visivel && ultimo.estado === "concluido" ? estado.naoLidas + 1 : estado.naoLidas,
    };
    queueMicrotask(() => {
      if (destruida) return;
      void carregarLista();
      if (ultimo.incompleta) void recarregarConversa();
    });
  };

  /* --- o fluxo do turno ---------------------------------------------------- */

  const descarregar = () => {
    cancelarDescarga?.();
    cancelarDescarga = null;
    if (fila.length === 0) return;
    const eventos = fila;
    fila = [];
    despachar({ tipo: "eventos", eventos, em: agora() });
  };

  const receber = (dono: Fio, evento: EventoDoTurno) => {
    if (fio !== dono || destruida) return;
    if (evento.tipo === "estado.alterado" && Array.isArray(evento.recursos) && evento.recursos.length > 0) {
      dependencias.avisar?.(evento.recursos.filter((recurso) => typeof recurso === "string"));
    }
    fila.push(evento);
    if (ehFimDoTurno(evento)) {
      descarregar();
      return;
    }
    cancelarDescarga ??= agendar(() => {
      cancelarDescarga = null;
      descarregar();
    });
  };

  const fecharFio = () => {
    if (!fio) return;
    const antigo = fio;
    fio = null;
    antigo.assinatura?.fechar();
    fila = [];
    cancelarDescarga?.();
    cancelarDescarga = null;
    if (vigia !== null) clearInterval(vigia);
    vigia = null;
  };

  const verificarTurno = async (conversaId: string, turnoId: string) => {
    if (verificando) return;
    verificando = true;
    let terminou = false;
    try {
      const situacao = await transporte.estadoDoTurno(conversaId, turnoId);
      terminou = situacao.estado !== "em_andamento";
    } catch (causa) {
      terminou = causa instanceof ErroDoMotor && causa.categoria === "ausente";
    } finally {
      verificando = false;
    }
    if (terminou && estado.conversa.id === conversaId && estado.conversa.turno?.id === turnoId) {
      fecharFio();
      await recarregarConversa();
    }
  };

  function sincronizarFio() {
    const { id: conversaId, turno } = estado.conversa;
    const turnoId = turno?.id ?? null;
    if (fio && (fio.turnoId !== turnoId || fio.conversaId !== conversaId)) fecharFio();
    if (!conversaId || !turnoId || !turno || fio || destruida) return;

    const novo: Fio = { conversaId, turnoId, assinatura: null };
    fio = novo;
    const assinatura = transporte.assinar(conversaId, turnoId, turno.ultimoSeq, {
      aoEvento: (evento) => receber(novo, evento),
      aoMudarEstado: (conexao) => {
        if (fio !== novo) return;
        if (conexao === "aberta" || conexao === "reconectando") despachar({ tipo: "conexao", turnoId, estado: conexao });
      },
      aoFalhar: (falha) => {
        if (fio !== novo) return;
        if (falha.semAbrir || falha.caidaHaMs >= ESPERA_ANTES_DE_CONSULTAR_MS) void verificarTurno(conversaId, turnoId);
      },
    });
    if (fio !== novo) {
      assinatura.fechar();
      return;
    }
    novo.assinatura = assinatura;
    vigia = setInterval(() => {
      const atual = estado.conversa.turno;
      if (fio !== novo || !atual || atual.id !== turnoId) return;
      if (agora() - atual.ultimoEventoEm > SILENCIO_MAXIMO_MS) void verificarTurno(conversaId, turnoId);
    }, 30_000);
  }

  /* --- conversas ------------------------------------------------------------ */

  const definirLista = (mudancas: Partial<EstadoDaLista>) =>
    definir((atual) => ({ ...atual, lista: { ...atual.lista, ...mudancas } }));

  const buscarLista = async (): Promise<ListaDeConversas> => {
    const lista = await transporte.listar();
    const conversas = resumosValidos(lista?.conversas);
    definirLista({ carregamento: "pronta", atual: typeof lista?.atual === "string" ? lista.atual : null, conversas });
    // O backend dá nome à conversa depois da primeira mensagem: o cabeçalho acompanha.
    const aberta = conversas.find((conversa) => conversa.id === estado.conversa.id);
    if (aberta?.titulo?.trim() && aberta.titulo.trim() !== estado.conversa.titulo) {
      despachar({ tipo: "renomeou", id: aberta.id, titulo: aberta.titulo });
    }
    return { atual: typeof lista?.atual === "string" ? lista.atual : null, conversas };
  };

  const carregarLista = async (): Promise<ListaDeConversas | null> => {
    if (estado.lista.carregamento !== "pronta") definirLista({ carregamento: "carregando" });
    try {
      return await buscarLista();
    } catch {
      if (estado.lista.carregamento !== "pronta") definirLista({ carregamento: "falhou" });
      return null;
    }
  };

  const abrirConversa = async (id: string | null = null) => {
    geracao += 1;
    const minha = geracao;
    despachar({ tipo: "carregar", id });
    try {
      let alvo = id;
      if (!alvo) {
        const lista = await buscarLista();
        if (minha !== geracao) return;
        alvo = lista.atual ?? lista.conversas[0]?.id ?? null;
      }
      if (!alvo) {
        despachar({ tipo: "semConversa" });
        return;
      }
      const conversa = await transporte.ler(alvo);
      if (minha !== geracao) return;
      despachar({ tipo: "carregou", conversa, em: agora() });
    } catch (causa) {
      if (minha !== geracao) return;
      const erro = paraErroNaTela(causa);
      despachar({ tipo: "falhouAoCarregar", erro, ausente: erro.categoria === "ausente" });
    }
  };

  const recarregarConversa = async () => {
    const id = estado.conversa.id;
    if (!id) return;
    const minha = geracao;
    try {
      const conversa = await transporte.ler(id);
      if (minha !== geracao || estado.conversa.id !== id) return;
      despachar({ tipo: "carregou", conversa, em: agora() });
    } catch {
      // A conversa na tela continua; a próxima abertura tenta de novo.
    }
  };

  const criarConversa = async (): Promise<string | null> => {
    try {
      const nova = await transporte.criar();
      geracao += 1;
      despachar({ tipo: "carregou", conversa: nova, em: agora() });
      void carregarLista();
      return nova.id;
    } catch (causa) {
      mostrarAviso(paraErroNaTela(causa).mensagem, "erro");
      return null;
    }
  };

  const novaConversa = async () => (await criarConversa()) !== null;

  const apagarConversa = async (id: string) => {
    try {
      const resposta = await transporte.apagar(id);
      definirLista({ conversas: estado.lista.conversas.filter((c) => c.id !== id) });
      if (estado.conversa.id === id) {
        const proxima =
          (typeof resposta?.atual === "string" && resposta.atual !== id ? resposta.atual : null) ??
          estado.lista.conversas[0]?.id ??
          null;
        await abrirConversa(proxima);
      }
      void carregarLista();
      return true;
    } catch (causa) {
      mostrarAviso(paraErroNaTela(causa).mensagem, "erro");
      return false;
    }
  };

  const renomearConversa = async (id: string, titulo: string) => {
    const limpo = titulo.replace(/\s+/g, " ").trim().slice(0, 200);
    if (!limpo) return false;
    try {
      await transporte.renomear(id, limpo);
      despachar({ tipo: "renomeou", id, titulo: limpo });
      definirLista({ conversas: estado.lista.conversas.map((c) => (c.id === id ? { ...c, titulo: limpo } : c)) });
      return true;
    } catch (causa) {
      mostrarAviso(paraErroNaTela(causa).mensagem, "erro");
      return false;
    }
  };

  /* --- turnos --------------------------------------------------------------- */

  const podeMandar = () =>
    !estado.conversa.turno &&
    estado.online &&
    estado.disponibilidade.disponivel &&
    estado.conversa.carregamento !== "carregando";

  const postar = async (conversaId: string, pedido: PedidoDeTurno) => {
    try {
      const resposta = await transporte.enviar(conversaId, pedido);
      if (estado.conversa.id !== conversaId) return;
      if (resposta.anexado) {
        despachar({ tipo: "envioRecusado", idCliente: pedido.id_cliente });
        if (!pedido.acao && !estado.caixa.texto.trim()) {
          definir((atual) => ({ ...atual, caixa: { ...atual.caixa, texto: pedido.texto } }));
        }
        mostrarAviso(AVISO_DE_TURNO_RODANDO, "info");
        await recarregarConversa();
        return;
      }
      despachar({ tipo: "enviado", idCliente: pedido.id_cliente, turnoId: resposta.turno_id, em: agora() });
    } catch (causa) {
      despachar({ tipo: "envioFalhou", idCliente: pedido.id_cliente, erro: paraErroNaTela(causa) });
    }
  };

  const enviar = async (texto: string, opcoes: OpcoesDoEnvio = {}) => {
    const limpo = texto.trim().slice(0, LIMITE_DE_CARACTERES);
    if (!limpo || !podeMandar()) return false;
    const pedido: PedidoDeTurno = {
      texto: limpo,
      ...(opcoes.contexto ? { contexto: opcoes.contexto } : {}),
      ...(opcoes.acao ? { acao: opcoes.acao } : {}),
      id_cliente: gerarId(),
    };
    definir((atual) => (atual.aviso ? { ...atual, aviso: null } : atual));
    // A bolha dela e os pontinhos aparecem no mesmo instante, antes de qualquer
    // ida ao servidor, inclusive a que cria a conversa na primeira mensagem.
    despachar({ tipo: "enviar", pedido, em: agora() });
    const conversaId = estado.conversa.id ?? (await criarConversa());
    if (!conversaId) {
      // A conversa não pôde ser criada: a bolha sai, e quem chamou devolve o texto.
      despachar({ tipo: "semConversa" });
      return false;
    }
    await postar(conversaId, pedido);
    return true;
  };

  const enviarDaCaixa = async () => {
    const { texto, contexto } = estado.caixa;
    if (!texto.trim() || !podeMandar()) return false;
    definir((atual) => ({ ...atual, caixa: { ...atual.caixa, texto: "", contexto: null } }));
    const foi = await enviar(texto, { contexto });
    if (!foi) {
      // Não saiu (a conversa não pôde ser criada): o texto volta para a caixa.
      definir((atual) => ({ ...atual, caixa: { ...atual.caixa, texto, contexto } }));
    }
    return foi;
  };

  const enviarSugestao = async (opcao: OpcaoSugerida) => {
    const { contexto } = estado.caixa;
    const foi = await enviar(opcao.texto, { contexto, ...(opcao.acao ? { acao: opcao.acao } : {}) });
    // O contexto vai uma vez, com a primeira mensagem sobre ele.
    if (foi && contexto) definir((atual) => ({ ...atual, caixa: { ...atual.caixa, contexto: null } }));
    return foi;
  };

  const reenviar = async (idCliente: string) => {
    const conversaId = estado.conversa.id;
    const bolha = estado.conversa.itens.find((item) => item.tipo === "senhora" && item.idCliente === idCliente);
    if (!conversaId || bolha?.tipo !== "senhora" || !bolha.pedido || !podeMandar()) return;
    despachar({ tipo: "reenviar", idCliente, em: agora() });
    if (estado.conversa.turno?.idCliente !== idCliente) return;
    await postar(conversaId, bolha.pedido);
  };

  const perguntarDeNovo = async (chave: string) => {
    const itens = estado.conversa.itens;
    const indice = itens.findIndex((item) => item.chave === chave);
    const resposta = itens[indice];
    if (resposta?.tipo !== "consultora") return;
    const idCliente = resposta.pedido?.id_cliente;
    if (idCliente && itens.some((item) => item.tipo === "senhora" && item.idCliente === idCliente)) {
      await reenviar(idCliente);
      return;
    }
    const pergunta = itens
      .slice(0, indice)
      .reverse()
      .find((item) => item.tipo === "senhora");
    if (pergunta?.tipo === "senhora" && pergunta.texto) {
      await enviar(pergunta.texto, { contexto: pergunta.contexto });
    }
  };

  const parar = async () => {
    const { id: conversaId, turno } = estado.conversa;
    if (!conversaId || !turno?.id || turno.fase === "cancelando") return;
    despachar({ tipo: "parar" });
    try {
      await transporte.parar(conversaId, turno.id);
    } catch {
      despachar({ tipo: "pararFalhou" });
      mostrarAviso("Não consegui parar agora. Tente de novo.", "erro");
    }
  };

  /* --- o resto ---------------------------------------------------------------- */

  const verificarDisponibilidade = async () => {
    if (novaVerificacao !== null) clearTimeout(novaVerificacao);
    novaVerificacao = null;
    try {
      const situacao = await transporte.estadoDoChat();
      const disponivel = situacao?.disponivel !== false;
      const motivo = disponivel ? null : textoParaEla(situacao?.motivo, MOTIVO_FORA_DO_AR);
      const modelo = typeof situacao?.modelo === "string" && situacao.modelo.trim() ? situacao.modelo.trim() : null;
      definir((atual) => ({ ...atual, disponibilidade: { disponivel, motivo, modelo, conferida: true } }));
      if (!disponivel && !destruida) {
        novaVerificacao = setTimeout(() => void verificarDisponibilidade(), NOVA_VERIFICACAO_MS);
      }
    } catch {
      // Sem saber, não trava: se ela mandar e der errado, o envio avisa.
    }
  };

  const trocarConversa = async (id: string) => {
    if (estado.conversa.id === id && estado.conversa.carregamento === "pronto") return;
    await abrirConversa(id);
    if (estado.conversa.id !== id || estado.conversa.carregamento !== "pronto") return;
    definirLista({ atual: id });
    try {
      await transporte.marcarAtual(id);
    } catch {
      // Marcar a atual é conforto: se falhar, a conversa abre do mesmo jeito.
    }
  };

  const esquecerConversas = () => {
    geracao += 1;
    despachar({ tipo: "semConversa" });
    definirLista({ carregamento: "pronta", atual: null, conversas: [] });
    void carregarLista();
  };

  const apagarTodas = async () => {
    try {
      const lista = await transporte.listar();
      for (const { id } of resumosValidos(lista?.conversas)) await transporte.apagar(id);
      geracao += 1;
      despachar({ tipo: "semConversa" });
      definirLista({ carregamento: "pronta", atual: null, conversas: [] });
      return true;
    } catch (causa) {
      mostrarAviso(paraErroNaTela(causa).mensagem, "erro");
      return false;
    } finally {
      void carregarLista();
    }
  };

  const loja: Loja = {
    ler: () => estado,
    assinar: (ouvinte) => {
      ouvintes.add(ouvinte);
      return () => {
        ouvintes.delete(ouvinte);
      };
    },
    ativar: () => {
      if (ativada || destruida) return;
      ativada = true;
      if (estado.conversa.carregamento === "vazio" || estado.conversa.carregamento === "falhou") {
        void abrirConversa(estado.conversa.id);
      } else {
        void carregarLista();
      }
      void verificarDisponibilidade();
    },
    abrirConversa,
    recarregarConversa,
    carregarLista,
    novaConversa,
    apagarConversa,
    renomearConversa,
    enviar,
    enviarDaCaixa,
    enviarSugestao,
    trocarConversa,
    apagarTodas,
    esquecerConversas,
    verificarDisponibilidade,
    reenviar,
    perguntarDeNovo,
    parar,
    definirTexto: (texto) =>
      definir((atual) =>
        atual.caixa.texto === texto
          ? atual
          : { ...atual, caixa: { ...atual.caixa, texto: texto.slice(0, LIMITE_DE_CARACTERES) } },
      ),
    definirContexto: (contexto) => definir((atual) => ({ ...atual, caixa: { ...atual.caixa, contexto } })),
    preencher: ({ rascunho, contexto }) =>
      definir((atual) => ({
        ...atual,
        caixa: {
          texto: typeof rascunho === "string" && rascunho.trim() ? rascunho.slice(0, LIMITE_DE_CARACTERES) : atual.caixa.texto,
          contexto: contexto === undefined ? atual.caixa.contexto : contexto,
          foco: atual.caixa.foco + 1,
        },
      })),
    pedirFoco: () => definir((atual) => ({ ...atual, caixa: { ...atual.caixa, foco: atual.caixa.foco + 1 } })),
    definirPainel: (aberto) =>
      definir((atual) => (atual.painelAberto === aberto ? atual : { ...atual, painelAberto: aberto })),
    definirVisivel: (agoraVisivel) => {
      visivel = agoraVisivel;
      if (agoraVisivel) definir((atual) => (atual.naoLidas === 0 ? atual : { ...atual, naoLidas: 0 }));
    },
    definirOnline: (online) => definir((atual) => (atual.online === online ? atual : { ...atual, online })),
    verificarEmSegundoPlano: async () => {
      if (ativada || destruida || estado.conversa.carregamento !== "vazio") return;
      try {
        const lista = await buscarLista();
        const atual = lista.conversas.find((c) => c.id === lista.atual);
        if (atual?.respondendo && !ativada && estado.conversa.carregamento === "vazio") await abrirConversa(atual.id);
      } catch {
        // Em segundo plano: se não der, a conversa carrega quando ela abrir.
      }
    },
    limparAviso: () => definir((atual) => (atual.aviso ? { ...atual, aviso: null } : atual)),
    destruir: () => {
      fecharFio();
      if (novaVerificacao !== null) clearTimeout(novaVerificacao);
      novaVerificacao = null;
      destruida = true;
      ouvintes.clear();
    },
  };
  return loja;
}
