/**
 * Chip de estado, e o selo de viabilidade.
 *
 * Os tons usam a cor semântica a 10% como fundo e a cor cheia como texto. O
 * teste de contraste confere esse par nos dois temas, sobre o cartão e sobre o
 * fundo cinza: antes, o chip de atenção dava 4,10:1 e o de info 4,33:1.
 */

import {
  CheckCircle,
  Prohibit,
  Question,
  ShoppingCartSimple,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";
import type { ReactNode } from "react";

import type { Veredito } from "@/lib/formato";
import { ROTULO_DO_VEREDITO, TOM_DO_VEREDITO } from "@/lib/formato";

export type TomDoChip = "neutro" | "marca" | "sucesso" | "atencao" | "perigo" | "info";

const TONS: Record<TomDoChip, string> = {
  neutro: "border-borda bg-secao text-texto",
  marca: "border-marca/25 bg-marca/10 text-marca-escura",
  sucesso: "border-sucesso/25 bg-sucesso/10 text-sucesso",
  atencao: "border-atencao/25 bg-atencao/10 text-atencao",
  perigo: "border-perigo/25 bg-perigo/10 text-perigo",
  info: "border-info/25 bg-info/10 text-info",
};

export function Chip({
  children,
  tom = "neutro",
  icone,
  className,
}: {
  children: ReactNode;
  tom?: TomDoChip;
  /** Ícone decorativo antes do texto: o texto continua dizendo tudo. */
  icone?: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-0.5",
        "text-xs leading-5 font-semibold whitespace-nowrap",
        TONS[tom],
        className,
      )}
    >
      {icone ? (
        <span aria-hidden="true" className="inline-flex shrink-0">
          {icone}
        </span>
      ) : null}
      <span className="truncate">{children}</span>
    </span>
  );
}

const ICONE_DO_VEREDITO: Record<Veredito, ReactNode> = {
  APTO: <CheckCircle size={14} weight="fill" />,
  "APTO COM COMPRA": <ShoppingCartSimple size={14} weight="fill" />,
  "FALTA INFO": <Question size={14} weight="fill" />,
  BLOQUEADO: <Prohibit size={14} weight="fill" />,
};

/**
 * Selo de viabilidade: se dá para fazer o prato.
 *
 * Mostra o rótulo dela ("Dá pra fazer"), nunca o valor técnico. Nunca usa o
 * vermelho da marca: no iFood o vermelho significa *ação*, e aqui "Não dá"
 * significa *impedimento*. Misturar os dois faria ler bloqueio como botão.
 * A cor nunca está sozinha: o ícone e o texto dizem o mesmo.
 */
export function SeloVeredito({
  veredito,
  rotulo,
  className,
}: {
  veredito: Veredito;
  /** O `veredito_rotulo` da API. Sem ele, o rótulo padrão do mesmo veredito. */
  rotulo?: string;
  className?: string;
}) {
  return (
    <Chip tom={TOM_DO_VEREDITO[veredito]} icone={ICONE_DO_VEREDITO[veredito]} className={className}>
      {rotulo ?? ROTULO_DO_VEREDITO[veredito]}
    </Chip>
  );
}
