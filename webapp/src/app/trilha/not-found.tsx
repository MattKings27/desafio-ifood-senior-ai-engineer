import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";

export default function NaoEncontrado() {
  return (
    <NaoEncontrada
      titulo="Não encontrei isso no histórico"
      descricao="O endereço pode ter mudado. O histórico inteiro continua aqui."
      voltar={{ href: "/trilha", rotulo: "Ver o histórico" }}
    />
  );
}
