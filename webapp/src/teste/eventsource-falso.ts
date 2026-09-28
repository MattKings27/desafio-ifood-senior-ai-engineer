/**
 * Um `EventSource` de mentira, para os testes do fluxo de eventos.
 *
 * O jsdom não tem `EventSource`. Este dublê guarda cada conexão aberta, e o
 * teste manda nela o que o servidor mandaria: abrir, um evento (com `id:`),
 * uma queda. Assim a reconexão, a espera crescente e o "sem repetição" são
 * testados de verdade, sem rede.
 *
 *     const fonte = EventSourceFalso.ultima();
 *     fonte.abrir();
 *     fonte.emitir({ seq: 1, tipo: "turno.iniciado" });
 *     fonte.cair();
 */

type Ouvinte = (evento: Event) => void;

export class EventSourceFalso {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  /** Todas as conexões criadas desde o último `reiniciar()`, na ordem. */
  static instancias: EventSourceFalso[] = [];

  static reiniciar() {
    EventSourceFalso.instancias = [];
  }

  /** A conexão mais recente (a que o código em teste está usando). */
  static ultima(): EventSourceFalso {
    const ultima = EventSourceFalso.instancias.at(-1);
    if (!ultima) throw new Error("nenhum EventSource foi criado");
    return ultima;
  }

  /** As conexões que ainda não foram fechadas. */
  static abertas(): EventSourceFalso[] {
    return EventSourceFalso.instancias.filter((fonte) => !fonte.fechada);
  }

  readonly url: string;
  readonly withCredentials = false;
  readyState = EventSourceFalso.CONNECTING;
  fechada = false;
  onopen: ((evento: Event) => void) | null = null;
  onmessage: ((evento: MessageEvent) => void) | null = null;
  onerror: ((evento: Event) => void) | null = null;
  private readonly ouvintes = new Map<string, Set<Ouvinte>>();

  constructor(url: string | URL) {
    this.url = String(url);
    EventSourceFalso.instancias.push(this);
  }

  addEventListener(tipo: string, ouvinte: Ouvinte) {
    let conjunto = this.ouvintes.get(tipo);
    if (!conjunto) {
      conjunto = new Set();
      this.ouvintes.set(tipo, conjunto);
    }
    conjunto.add(ouvinte);
  }

  removeEventListener(tipo: string, ouvinte: Ouvinte) {
    this.ouvintes.get(tipo)?.delete(ouvinte);
  }

  dispatchEvent(evento: Event): boolean {
    for (const ouvinte of this.ouvintes.get(evento.type) ?? []) ouvinte(evento);
    return true;
  }

  close() {
    this.readyState = EventSourceFalso.CLOSED;
    this.fechada = true;
  }

  /* --- o que o "servidor" faz ---------------------------------------------- */

  abrir() {
    if (this.fechada) return;
    this.readyState = EventSourceFalso.OPEN;
    const evento = new Event("open");
    this.onopen?.(evento);
    this.dispatchEvent(evento);
  }

  /** Um evento `data:`; objetos viram JSON. `id` é o `id:` do SSE. */
  emitir(dados: unknown, id?: string | number) {
    if (this.fechada) return;
    const evento = new MessageEvent("message", {
      data: typeof dados === "string" ? dados : JSON.stringify(dados),
      lastEventId: id === undefined ? "" : String(id),
    });
    this.onmessage?.(evento);
    this.dispatchEvent(evento);
  }

  /** A conexão caiu (ou o servidor recusou o fluxo). */
  cair() {
    if (this.fechada) return;
    this.readyState = EventSourceFalso.CONNECTING;
    const evento = new Event("error");
    this.onerror?.(evento);
    this.dispatchEvent(evento);
  }
}

/** Troca o `EventSource` global pelo falso e devolve como desfazer. */
export function instalarEventSourceFalso(): () => void {
  const alvo = globalThis as { EventSource?: unknown };
  const antes = alvo.EventSource;
  alvo.EventSource = EventSourceFalso;
  EventSourceFalso.reiniciar();
  return () => {
    alvo.EventSource = antes;
    EventSourceFalso.reiniciar();
  };
}

/** O fabricante que o `assinarFluxo` aceita em `criar`. */
export function criarEventSourceFalso(url: string): EventSource {
  return new EventSourceFalso(url) as unknown as EventSource;
}
