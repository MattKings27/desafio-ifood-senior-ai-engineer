/**
 * Junta as classes padrão de uma primitiva com as de quem a usa, deixando as
 * de quem usa vencerem.
 *
 * No Tailwind, duas classes da mesma propriedade (`bg-superficie` e
 * `bg-info/5`) não se resolvem pela ordem no `className`, e sim pela ordem no
 * CSS gerado. Um `<Card className="bg-creme">` podia continuar branco. Aqui,
 * quando quem usa passa uma classe de um destes grupos (fundo, cor da borda,
 * sombra, espaçamento interno), a padrão do mesmo grupo, com as mesmas
 * variantes (`hover:`, `sm:`…), sai.
 */

import clsx, { type ClassValue } from "clsx";

const LARGURA_OU_ESTILO =
  /^(?:[trblxyse]|[0-9]+|dashed|dotted|solid|double|none|hidden|collapse|separate|spacing)(?:-|$)/;

function grupoDe(classe: string): string | null {
  const partes = classe.split(":");
  const utilitaria = partes.pop() ?? "";
  const variantes = partes.join(":");
  const sem = utilitaria.replace(/^!/, "");

  let grupo: string | null = null;
  if (/^bg-(?!(?:clip|origin|repeat|no-repeat|fixed|local|scroll|auto|cover|contain|center|top|bottom|left|right|blend|linear|radial|conic|gradient|none|size|position)(?:-|$))/.test(sem)) {
    grupo = "fundo";
  } else if (sem.startsWith("border-") && !LARGURA_OU_ESTILO.test(sem.slice("border-".length))) {
    grupo = "cor-da-borda";
  } else if (/^shadow(?:-|$)/.test(sem)) {
    grupo = "sombra";
  } else if (/^p-/.test(sem)) {
    grupo = "espaco";
  }
  return grupo ? `${variantes}|${grupo}` : null;
}

export function unirClasses(padrao: ClassValue, deQuemUsa?: ClassValue): string {
  const extras = clsx(deQuemUsa).split(/\s+/).filter(Boolean);
  const gruposDeQuemUsa = new Set(extras.map(grupoDe).filter((g): g is string => g !== null));
  const base = clsx(padrao)
    .split(/\s+/)
    .filter(Boolean)
    .filter((classe) => {
      const grupo = grupoDe(classe);
      return grupo === null || !gruposDeQuemUsa.has(grupo);
    });
  return [...base, ...extras].join(" ");
}
