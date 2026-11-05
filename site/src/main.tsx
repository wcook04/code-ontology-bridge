import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/source-sans-3/wght.css";
import "@fontsource/stix-two-text/500.css";
import "@fontsource/jetbrains-mono/400.css";

import "./styles/tokens.css";
// The parts every one of Will Cook's websites shares, copied unchanged from lean-exposition; tokens.css maps their names.
import "./styles/family.css";
import "./styles/app.css";

import { App } from "./app/App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
