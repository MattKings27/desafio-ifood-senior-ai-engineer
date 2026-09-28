import { NaoEncontrada } from "@/componentes/globais/NaoEncontrada";

export default function ReceitaNaoEncontrada() {
  return (
    <NaoEncontrada
      titulo="Não encontrei esta receita"
      descricao="Ela pode ter sido tirada, ou o endereço mudou. As receitas que a senhora consegue fazer estão na lista."
      voltar={{ href: "/receitas", rotulo: "Ver as receitas" }}
    />
  );
}
