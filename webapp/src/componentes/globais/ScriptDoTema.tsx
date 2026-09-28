/**
 * O script do `<head>` que marca a aparência antes da primeira pintura: o
 * tema, o tamanho do texto, o movimento e o modo minimalista que ela escolheu
 * nas Preferências.
 *
 * É um server component de propósito: o `<script>` sai no HTML e roda enquanto
 * o navegador lê a página, antes do React existir. O layout raiz não remonta
 * na navegação, então ele roda uma vez por carga da página, que é o que basta.
 */

import { SCRIPT_DA_APARENCIA } from "@/lib/preferencias";

export function ScriptDoTema() {
  return <script id="script-do-tema" dangerouslySetInnerHTML={{ __html: SCRIPT_DA_APARENCIA }} />;
}
