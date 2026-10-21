import "@fontsource-variable/inter";
import "@fontsource-variable/source-serif-4";
import "@fontsource/jetbrains-mono/400.css";
import "./styles/tokens.css";
import "./styles/global.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
