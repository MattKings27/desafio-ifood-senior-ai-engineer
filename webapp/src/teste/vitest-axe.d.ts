/**
 * O `vitest-axe` estende `expect` em tempo de execução, mas não publica a
 * declaração do matcher para o TypeScript. Sem isto, `toHaveNoViolations` só
 * existe para o runtime e o `tsc --noEmit` reprova. Reprovar é o certo, e o
 * conserto é declarar, não afrouxar o modo estrito.
 */
import type { AxeMatchers } from "vitest-axe/matchers";

declare module "vitest" {
  // O parâmetro de tipo existe para casar com a declaração do próprio vitest;
  // esta augmentação não o usa, e é assim mesmo.
  /* eslint-disable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars */
  interface Assertion<T = unknown> extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
  /* eslint-enable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars */
}
