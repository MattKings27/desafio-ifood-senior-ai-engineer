/**
 * A foto de um ingrediente, ou, sem foto, o gradiente com o ícone da categoria.
 *
 * A foto vem só da API (`/motor/imagens/<chave>`), pela `ImagemComFallback`.
 * Enquanto a busca de fotos não traz uma, cada categoria tem o seu desenho:
 * um ovo para carnes e ovos, uma cenoura para o hortifrúti. A proporção é a
 * mesma nos dois casos, então a grade não pula quando a foto chega.
 */

import {
  Basket,
  Cake,
  Carrot,
  Cheese,
  Drop,
  Egg,
  Grains,
  Jar,
  Pepper,
} from "@phosphor-icons/react/dist/ssr";
import clsx from "clsx";

import { ImagemComFallback } from "@/componentes/compartilhados/ImagemComFallback";
import type { Imagem } from "@/lib/api/base";

type Desenho = { Icone: typeof Basket; fundo: string; cor: string };

/** Cada categoria da despensa com o seu ícone e a sua tinta (classes inteiras, para o Tailwind achar). */
const DESENHOS: Readonly<Record<string, Desenho>> = {
  proteinas: { Icone: Egg, fundo: "from-marca/15", cor: "text-marca" },
  graos: { Icone: Grains, fundo: "from-atencao/15", cor: "text-atencao" },
  hortifruti: { Icone: Carrot, fundo: "from-sucesso/15", cor: "text-sucesso" },
  laticinios: { Icone: Cheese, fundo: "from-info/15", cor: "text-info" },
  temperos: { Icone: Pepper, fundo: "from-perigo/15", cor: "text-perigo" },
  oleos: { Icone: Drop, fundo: "from-atencao/10", cor: "text-atencao" },
  conservas: { Icone: Jar, fundo: "from-sucesso/10", cor: "text-sucesso" },
  confeitaria: { Icone: Cake, fundo: "from-marca/10", cor: "text-marca" },
};

const SEM_CATEGORIA: Desenho = { Icone: Basket, fundo: "from-secao", cor: "text-apagado" };

export function desenhoDaCategoria(categoria: string): Desenho {
  return DESENHOS[categoria] ?? SEM_CATEGORIA;
}

export function FotoDoIngrediente({
  imagem,
  categoria,
  alt = "",
  mostrarCredito = false,
  prioridade = false,
  grande = false,
  className,
}: {
  imagem: Imagem;
  categoria: string;
  /** Vazio quando o nome está ao lado da foto (no cartão e na página do item). */
  alt?: string;
  mostrarCredito?: boolean;
  prioridade?: boolean;
  /** O ícone maior, na página do item. */
  grande?: boolean;
  className?: string;
}) {
  if (imagem) {
    return (
      <ImagemComFallback
        src={imagem.url}
        alt={alt}
        credito={imagem.credito}
        mostrarCredito={mostrarCredito}
        prioridade={prioridade}
        tipo="ingrediente"
        proporcao="4/3"
        className={className}
      />
    );
  }
  const { Icone, fundo, cor } = desenhoDaCategoria(categoria);
  return (
    <div
      aria-hidden="true"
      data-sem-foto=""
      className={clsx(
        "relative flex aspect-[4/3] w-full items-center justify-center overflow-hidden bg-linear-to-br to-creme",
        fundo,
        className,
      )}
    >
      <Icone size={grande ? 72 : 44} weight="duotone" className={cor} />
    </div>
  );
}
