/**
 * "Não encontrei": o endereço não existe, ou o item foi tirado.
 *
 * Usada pelo `not-found.tsx` da raiz e pelos das páginas de detalhe
 * (`/despensa/[id]`, `/receitas/[slug]`), que chamam `notFound()` quando a API
 * responde com a categoria `ausente`.
 */

import { House, MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";

import { BotaoLink } from "@/componentes/compartilhados/BotaoLink";
import { EstadoVazio } from "@/componentes/compartilhados/EstadoVazio";

export function NaoEncontrada({
  titulo = "Não encontrei esta página",
  descricao = "O endereço pode ter mudado, ou o que estava aqui foi tirado.",
  voltar = { href: "/", rotulo: "Voltar ao início" },
}: {
  titulo?: string;
  descricao?: string;
  voltar?: { href: string; rotulo: string };
}) {
  return (
    <div className="mx-auto max-w-xl py-6">
      <EstadoVazio
        titulo={titulo}
        nivelTitulo={1}
        descricao={descricao}
        icone={<MagnifyingGlass size={24} weight="duotone" />}
        acao={
          <BotaoLink href={voltar.href} icone={<House size={18} weight="bold" />}>
            {voltar.rotulo}
          </BotaoLink>
        }
      />
    </div>
  );
}
