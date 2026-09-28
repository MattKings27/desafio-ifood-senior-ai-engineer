import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";

export default function NaoEncontrado() {
  return (
    <NaoEncontrada
      titulo="Não encontrei este prato"
      descricao="A receita pode ter sido tirada. Dá para escrever a receita de novo e pôr o preço."
      voltar={{ href: "/precificar", rotulo: "Pôr preço num prato" }}
    />
  );
}
