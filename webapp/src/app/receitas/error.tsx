"use client";

import type { PropsDoErroDaRota } from "@/componentes/globais/ErroDaPagina";
import { ErroDaPagina } from "@/componentes/globais/ErroDaPagina";

export default function ErroReceitas(props: PropsDoErroDaRota) {
  return <ErroDaPagina {...props} titulo="Não consegui abrir as receitas" />;
}
