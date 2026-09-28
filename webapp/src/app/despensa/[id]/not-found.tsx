import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";

export default function IngredienteNaoEncontrado() {
  return (
    <NaoEncontrada
      titulo="Não encontrei este ingrediente"
      descricao="Ele pode ter saído da despensa. Na lista está tudo o que a senhora tem agora."
      voltar={{ href: "/despensa", rotulo: "Ver a despensa" }}
    />
  );
}
