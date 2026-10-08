import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import Admin from "./Admin";
import App from "./App";
import "./styles.css";

function Rota() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const f = () => setHash(location.hash);
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  return hash === "#/admin" ? <Admin /> : <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Rota />
  </StrictMode>,
);
