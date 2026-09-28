# Depois das primeiras correções

Os mesmos 12 cenários, k = 1, `claude-opus-5` com esforço `max`, agora com as
primeiras correções (a conta e o portão no motor; as instruções, o guard-rail e o
perfil da agente), rodando fora do repositório.

| | antes | depois |
|---|---|---|
| Passaram | 8 de 12 | **9 de 12** |
| Números certos apagados pelo guard-rail | 18 | 10 |
| Latência por turno (p50 / p95) | 64 s / 142 s | 59.8 s / 119.4 s |
| Custo da rodada | ≈ US$ 7 | ≈ US$ 8.50 |

O caminho completo agora sai certo de ponta a ponta: portão, custo de R$ 2,47,
mínimo de R$ 2,75 (antes a agente dizia R$ 2,74, que dá prejuízo) e o aceite
gravado com o preço e o lucro.

## As três falhas, e o que cada uma mudou

- **Números apagados** (caminho completo, preço abaixo do mínimo). Dos 10, parte
  foi a agente fazendo conta com os números do motor ("a diferença entre os dois é
  tanto", "o frango teria que ir a tanto o quilo") ou inventando exemplo: o
  guard-rail acertou em apagar. O resto foi lacuna do motor: para um preço que ela
  mesma propõe, nenhuma ferramenta devolvia a taxa e o que chega para ela. Agora
  `testar_sensibilidade` devolve a conta completa do preço proposto, e o `SOUL.md`
  diz para não derivar número.
- **Aceite registrado sem ela decidir.** Ela perguntou "pode ser?" e a agente já
  gravou o aceite. O `SOUL.md` agora manda mostrar a conta e perguntar se fica.
- **Ferramentas de arquivo.** Para achar a planilha, a agente usou `search_files`
  e `read_file` na pasta pessoal e no repositório: o perfil herdava o pacote
  inteiro do Hermes. O overlay agora desliga arquivo, terminal, código, navegador
  e controle do computador, e o harness conta o uso de qualquer uma como falha.

## Cenários corrigidos depois desta rodada

- `preco-abaixo-do-minimo` usava R$ 3,00, que fica acima do mínimo deste prato
  (R$ 2,75). Agora usa R$ 2,50. A reavaliação desta rodada julga a transcrição de
  R$ 3,00 pelo comportamento: o aceite gravado sem ela confirmar.
- `nao-gosta-encerra-o-prato` proibia qualquer valor em reais; a agente citou a
  despensa com os números do motor, o que é legítimo.
- `receitas-da-web-com-a-despensa` exigia `https://`; a agente citou o endereço
  sem o esquema.

A primeira leitura deu 8 de 12; com os cenários corrigidos e reavaliados sem rodar
de novo, 9 de 12.
