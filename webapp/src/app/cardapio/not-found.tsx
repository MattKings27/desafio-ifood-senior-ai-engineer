import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";

export default function NaoEncontrado() {
  return (
    <NaoEncontrada
      titulo="Não encontrei este prato"
      descricao="Ele pode ter saído do cardápio. Os pratos que a senhora aceitou estão no cardápio."
      voltar={{ href: "/cardapio", rotulo: "Ver o cardápio" }}
    />
  );
}
