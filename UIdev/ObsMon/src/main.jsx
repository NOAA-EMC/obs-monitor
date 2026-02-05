import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from 'react-router-dom';  // <-- use HashRouter instead of BrowserRouter

import App from "./App";
import "./index.css";
import { ModelProvider } from "./components/ModelContext";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <HashRouter>
      <ModelProvider>
        <App />
      </ModelProvider>
    </HashRouter>
  </React.StrictMode>
);
71187118
