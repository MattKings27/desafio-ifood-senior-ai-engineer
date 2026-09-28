"use client";

import type { PropsDoErroDaRota } from "@/componentes/globais/ErroDaPagina";
import { ErroDaPagina } from "@/componentes/globais/ErroDaPagina";

export default function ErroDespensa(props: PropsDoErroDaRota) {
  return <ErroDaPagina {...props} titulo="Não consegui abrir a despensa" />;
}
