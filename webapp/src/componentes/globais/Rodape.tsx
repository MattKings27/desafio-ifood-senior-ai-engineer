/**
 * O rodapé e o link de pular para o conteúdo.
 *
 * A frase do rodapé é a promessa que a tela inteira cumpre: todo número vem da
 * conta feita a partir da planilha dela, com a conta ao lado.
 */

export function LinkPular() {
  return (
    <a
      href="#conteudo"
      className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:rounded-sm focus:bg-marca-fundo focus:px-4 focus:py-3 focus:text-sm focus:font-bold focus:text-sobre-marca"
    >
      Pular para o conteúdo
    </a>
  );
}

export function Rodape() {
  return (
    <footer className="border-t border-borda">
      <p className="mx-auto max-w-6xl px-4 py-6 text-sm text-apagado sm:px-6">
        Todo valor nesta tela vem da conta feita a partir da sua planilha, com a conta ao lado. A
        interface não faz nenhuma conta.
      </p>
    </footer>
  );
}
