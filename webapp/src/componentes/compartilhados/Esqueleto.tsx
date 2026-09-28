/**
 * Esqueletos: a forma da tela enquanto os dados chegam.
 *
 * Cada peça é decorativa (`aria-hidden`). Quem anuncia o carregamento é o
 * `EsqueletoDaPagina`, uma vez, com `role="status"`. O brilho respeita o
 * "reduzir movimento" (ver `globals.css`).
 */

import clsx from "clsx";

export function Esqueleto({
  className,
  forma = "bloco",
}: {
  className?: string;
  forma?: "bloco" | "linha" | "circulo";
}) {
  const temAltura = /(?:^|\s)(?:h-|size-|aspect-)/.test(className ?? "");
  return (
    <div
      aria-hidden="true"
      className={clsx(
        "esqueleto animate-brilho",
        forma === "circulo" ? "rounded-full" : forma === "linha" ? "rounded-xs" : "rounded-sm",
        forma === "linha" && !temAltura && "h-4",
        className,
      )}
    />
  );
}

const LARGURAS = ["w-full", "w-11/12", "w-4/5", "w-2/3", "w-3/4"] as const;

export function EsqueletoTexto({ linhas = 3, className }: { linhas?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={clsx("space-y-2", className)}>
      {Array.from({ length: linhas }, (_, i) => (
        <Esqueleto key={i} forma="linha" className={i === linhas - 1 ? "w-1/2" : LARGURAS[i % LARGURAS.length]} />
      ))}
    </div>
  );
}

export function EsqueletoCartao({
  comImagem = false,
  className,
}: {
  comImagem?: boolean;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={clsx("overflow-hidden rounded-lg border border-borda bg-superficie", className)}
    >
      {comImagem ? <Esqueleto className="aspect-square w-full rounded-none" /> : null}
      <div className="space-y-2 p-4">
        <Esqueleto forma="linha" className="h-5 w-2/3" />
        <EsqueletoTexto linhas={2} />
      </div>
    </div>
  );
}

export function EsqueletoGrade({
  quantidade = 6,
  comImagem = true,
  className,
}: {
  quantidade?: number;
  comImagem?: boolean;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={clsx("grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-4", className)}
    >
      {Array.from({ length: quantidade }, (_, i) => (
        <EsqueletoCartao key={i} comImagem={comImagem} />
      ))}
    </div>
  );
}

export function EsqueletoLista({ linhas = 5, className }: { linhas?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={clsx("divide-y divide-borda", className)}>
      {Array.from({ length: linhas }, (_, i) => (
        <div key={i} className="flex items-center gap-3 py-3">
          <Esqueleto forma="circulo" className="size-10 shrink-0" />
          <div className="min-w-0 flex-1 space-y-2">
            <Esqueleto forma="linha" className="w-1/2" />
            <Esqueleto forma="linha" className="h-3 w-1/3" />
          </div>
          <Esqueleto forma="linha" className="w-16" />
        </div>
      ))}
    </div>
  );
}

export type VarianteDoEsqueleto = "grade" | "lista" | "detalhe" | "painel";

/** A página inteira carregando: título, apoio e o miolo da variante. */
export function EsqueletoDaPagina({
  variante = "painel",
  rotulo = "Carregando…",
}: {
  variante?: VarianteDoEsqueleto;
  /** O que o leitor de tela anuncia. */
  rotulo?: string;
}) {
  return (
    <div role="status" aria-live="polite" className="space-y-6">
      <span className="sr-only">{rotulo}</span>
      <div aria-hidden="true" className="space-y-3">
        <Esqueleto className="h-8 w-2/3 max-w-sm" />
        <Esqueleto forma="linha" className="w-full max-w-lg" />
      </div>
      {variante === "grade" ? <EsqueletoGrade /> : null}
      {variante === "lista" ? (
        <div className="rounded-lg border border-borda bg-superficie px-4">
          <EsqueletoLista />
        </div>
      ) : null}
      {variante === "detalhe" ? (
        <div aria-hidden="true" className="grid gap-6 lg:grid-cols-[2fr_3fr]">
          <Esqueleto className="aspect-[4/3] w-full rounded-lg" />
          <div className="space-y-4">
            <EsqueletoCartao />
            <EsqueletoCartao />
          </div>
        </div>
      ) : null}
      {variante === "painel" ? (
        <div aria-hidden="true" className="grid gap-4 md:grid-cols-2">
          <EsqueletoCartao />
          <EsqueletoCartao />
          <EsqueletoCartao className="md:col-span-2" />
        </div>
      ) : null}
    </div>
  );
}
