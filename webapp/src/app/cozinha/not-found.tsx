import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";

export default function CozinhaNaoEncontrada() {
  return (
    <NaoEncontrada
      titulo="Não encontrei isso na cozinha"
      descricao="O endereço pode ter mudado. Na cozinha está tudo o que a senhora já me contou."
      voltar={{ href: "/cozinha", rotulo: "Ver a cozinha" }}
    />
  );
}
