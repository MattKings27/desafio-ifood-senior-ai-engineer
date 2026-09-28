import type { MetadataRoute } from "next";

/** Para instalar na tela inicial do celular, como um aplicativo. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Sabor da Maria",
    short_name: "Sabor da Maria",
    description: "Consultoria de cardápio e preço para o delivery da Dona Maria.",
    lang: "pt-BR",
    start_url: "/",
    display: "standalone",
    background_color: "#f7f7f7",
    theme_color: "#ffffff",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
