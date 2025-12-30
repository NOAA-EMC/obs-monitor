import { useState } from "react";
import { useModel } from "./ModelContext";

export default function ModelComponentMenu() {
  const {
    model,
    setModel,
    component,
    setComponent,
    availableModels = [],
    availableComponents = [],
  } = useModel();

  const [openModel, setOpenModel] = useState(false);
  const [openComponent, setOpenComponent] = useState(false);

  const safeModels = Array.isArray(availableModels) ? availableModels : [];
  const safeComponents = Array.isArray(availableComponents) ? availableComponents : [];

  return (
    <div className="mb-4">
      {/* MODEL */}

      <button
        className="custom-button-category"
        onClick={() => setOpenModel(!openModel)}
      >
        <span>Model</span>
        {model && (
          <>
            :<span className="ml-2">{model}</span>
          </>
        )}
      </button>

      {openModel && safeModels.length > 0 && (
        <div className="ml-4 mt-1">
          {safeModels.map((m) => (
            <button
              key={m}
              className={"custom-button-instrument mb-2" + (model === m ? " font-bold" : "")}
              onClick={() => {
                setModel(m);
                setOpenModel(false);
                setOpenComponent(false);
              }}
            >
              {m}
            </button>
          ))}
        </div>
      )}

      {/* COMPONENT */}
      <button
        className="custom-button-category"
        onClick={() => setOpenComponent(!openComponent)}
      >
        <span>Component</span>
        {component && (
          <>
            :<span className="ml-2">{component}</span>
          </>
        )}
      </button>

      {openComponent && safeComponents.length > 0 && (
        <div className="ml-4 mt-1">
          {safeComponents.map((c) => (
            <button
              key={c}
              className={"custom-button-instrument mb-2" + (component === c ? " font-bold" : "")}
              onClick={() => {
                setComponent(c);
                setOpenComponent(false);
              }}
            >
              {c}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
