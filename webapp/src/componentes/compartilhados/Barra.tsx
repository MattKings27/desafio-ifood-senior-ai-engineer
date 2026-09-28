/**
 * Barra de proporção: quanto do orçamento foi, quanto do custo é cada item.
 *
 * É um `meter` com nome, e a fração vem da API: a barra só desenha. A cor de
 * preenchimento passa 3:1 contra o trilho nos dois temas (teste de contraste).
 */

import clsx from "clsx";

export type TomDaBarra = "marca" | "sucesso" | "atencao" | "perigo" | "info" | "neutro";

const CORES: Record<TomDaBarra, string> = {
  // Na barra, `bg-marca` é a cor de texto da marca, que passa 3:1 contra o
  // trilho também no escuro (ver a exceção da barra em globals.css).
  marca: "bg-marca",
  sucesso: "bg-sucesso",
  atencao: "bg-atencao",
  perigo: "bg-perigo",
  info: "bg-info",
  neutro: "bg-apagado",
};

export function Barra({
  fracao,
  tom = "marca",
  rotulo,
  valorTexto,
  espessura = "md",
  className,
}: {
  /** De 0 a 1. Fora disso, é presa nas pontas. */
  fracao: number;
  tom?: TomDaBarra;
  /** O nome do medidor, para o leitor de tela ("orçamento usado"). */
  rotulo?: string;
  /** Como ler o valor (ex.: "12% do que a senhora pagou"). */
  valorTexto?: string;
  espessura?: "sm" | "md" | "lg";
  className?: string;
}) {
  const presa = Number.isFinite(fracao) ? Math.max(0, Math.min(1, fracao)) : 0;
  const porcento = presa * 100;
  return (
    <div
      className={clsx(
        "w-full overflow-hidden rounded-full bg-borda",
        espessura === "sm" ? "h-1.5" : espessura === "lg" ? "h-3" : "h-2",
        className,
      )}
      role="meter"
      aria-valuenow={Math.round(porcento)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={valorTexto}
      aria-label={rotulo ?? "proporção"}
    >
      <div
        className={clsx("h-full rounded-full transition-[width] duration-padrao ease-padrao", CORES[tom])}
        style={{ width: `${porcento}%` }}
      />
    </div>
  );
}
