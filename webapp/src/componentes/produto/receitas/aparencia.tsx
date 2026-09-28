/**
 * O plano B da foto de uma receita: enquanto as fotos não chegam (ou quando
 * uma falha), a grade não vira uma parede de quadrados iguais. Cada receita
 * ganha um tom fixo, tirado do slug, e um ícone do tipo de prato, tirado do
 * nome. Tudo decorativo: o nome do prato está sempre escrito ao lado.
 */

import {
  Bread,
  BowlFood,
  BowlSteam,
  Cake,
  Cheese,
  Cookie,
  CookingPot,
  Egg,
  Fish,
  Grains,
  Hamburger,
  IceCream,
  Leaf,
  Pizza,
  Shrimp,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";

const TONS = [
  "bg-linear-to-br from-creme to-rosa/60 text-marca",
  "bg-linear-to-br from-creme to-atencao/25 text-atencao",
  "bg-linear-to-br from-creme to-sucesso/20 text-sucesso",
  "bg-linear-to-br from-creme to-info/20 text-info",
  "bg-linear-to-br from-secao to-creme text-apagado",
] as const;

const PRATOS: readonly [RegExp, Icon][] = [
  [/\b(?:bolo|pudim|brigadeiro|mousse|cupcake|quindim|doce)\b/, Cake],
  [/\b(?:biscoito|cookie|bolacha|sequilho)\b/, Cookie],
  [/\b(?:sopa|caldo|canja)\b/, BowlSteam],
  [/\b(?:peixe|tilapia|bacalhau|salmao|atum|sardinha|moqueca)\b/, Fish],
  [/\b(?:camarao|frutos do mar)\b/, Shrimp],
  [/\bpizza\b/, Pizza],
  [/\b(?:hamburguer|lanche|sanduiche)\b/, Hamburger],
  [/\b(?:pao|broa|rosca)\b/, Bread],
  [/\b(?:salada|legumes?|verduras?)\b/, Leaf],
  [/\b(?:ovos?|omelete|fritada)\b/, Egg],
  [/\b(?:sorvete|picole)\b/, IceCream],
  [/\bqueijo\b/, Cheese],
  [/\b(?:arroz|feijao|risoto|cuscuz|tropeiro|baiao)\b/, Grains],
  [/\b(?:carne|frango|escondidinho|strogonoff|estrogonofe|lasanha|ensopado|guisado|panela)\b/, CookingPot],
];

function semAcento(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** O tom da receita: sempre o mesmo para o mesmo slug. */
export function tomDaFoto(slug: string): string {
  let soma = 0;
  for (const letra of slug) soma = (soma * 31 + letra.charCodeAt(0)) % 9973;
  return TONS[soma % TONS.length] as string;
}

/** O ícone do tipo de prato, pelo nome; sem pista, uma tigela. */
export function IconeDoPrato({ nome, tamanho }: { nome: string; tamanho: number }) {
  const texto = semAcento(nome);
  const Icone = PRATOS.find(([padrao]) => padrao.test(texto))?.[1] ?? BowlFood;
  return <Icone size={tamanho} weight="duotone" />;
}
