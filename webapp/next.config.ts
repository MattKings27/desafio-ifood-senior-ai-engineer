import type { NextConfig } from "next";

const API = process.env.MISE_API ?? "http://127.0.0.1:8777";

const config: NextConfig = {
  reactStrictMode: true,
  // A API é a única fonte dos números. O proxy evita CORS no navegador e
  // mantém a origem única, então o front nunca precisa saber a porta da API.
  async rewrites() {
    return [
      { source: "/motor/:caminho*", destination: `${API}/api/:caminho*` },
      { source: "/saude/:caminho*", destination: `${API}/saude/:caminho*` },
    ];
  },
  experimental: {
    // O proxy do Next desiste em 30 s por padrão. Um turno do agente leva
    // de 30 a 90 s (com eventos a cada 10 s, no máximo), e trazer uma receita
    // da internet também passa disso às vezes.
    proxyTimeout: 120_000,
  },
  images: {
    // Nenhum endereço de fora: o curinga de antes ("**") fazia do otimizador
    // de imagens um proxy aberto para qualquer site. As fotos vêm cacheadas da
    // API, pela mesma origem, e a tela usa <img> comum com proporção fixa.
    remotePatterns: [],
    localPatterns: [{ pathname: "/motor/imagens/**", search: "" }],
  },
};

export default config;
