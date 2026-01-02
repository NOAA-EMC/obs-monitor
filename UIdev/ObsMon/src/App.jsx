import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu } from "lucide-react"; // hamburger icon
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "./data/channels.js";
import MainContent from "./MainContent.jsx";
import { withBase } from './utils/paths.js';
import { ATMOS_TYPES } from "./data/atmosTypes.js";
import { CONVENTIONAL_TYPES } from "./data/conventionalTypes.js";

import RadianceCategory from './components/RadianceCategory.jsx';
import OzoneObs from './components/OzoneObs.jsx';
import ConventionalObs from './components/ConventionalObs.jsx';


function App() {

  const navigate = useNavigate();
  const [model, setModel] = useState(null);
  const [component, setComponent] = useState(null);

  const go = (to) => {
    navigate(to);
    if (window.innerWidth < 1024) setSidebarOpen(false); // only close on mobile/tablet
  };

  const [modelsConfig, setModelsConfig] = useState(null);

  // Sidebar toggle for mobile
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [openSection, setOpenSection] = useState(null);
  const [openSat, setOpenSat] = useState(null);
  const [ozoneSatellites, setOzoneSatellites] = useState([]);
  const [microwaveSatellites, setMicrowaveSatellites] = useState([]);
  const [infraredSatellites, setInfraredSatellites] = useState([]);
  const [geostationarySatellites, setGeostationarySatellites] = useState([]);

  const [gpsTypes, setGpsTypes] = useState([]);
  const [psTypes, setPsTypes] = useState([]);
  const [qTypes, setQTypes] = useState([]);
  const [tTypes, setTTypes] = useState([]);
  const [uvTypes, setUvTypes] = useState([]);

  const [config, setConfig] = useState(null);

  const [cycleTime, setCycleTime] = useState(null);
  const previousCycle = useRef(null);

  const satSetters = {
    microwave: setMicrowaveSatellites,
    infrared: setInfraredSatellites,
    geostationary: setGeostationarySatellites,
    ozone: setOzoneSatellites
  };

  const convSetters = {
    gpstype: setGpsTypes,
    pstype: setPsTypes,
    qtype: setQTypes,
    ttype: setTTypes,
    uvtype: setUvTypes
  }

  useEffect(() => {
    fetch(withBase("data/models.json"), { cache: "no-store" })
      .then(res => res.json())
      .then(data => setModelsConfig(data))
      .catch(err => console.error("Failed to load models.json:", err));
  }, []);

  useEffect(() => {
    if (!model) {
      Object.values(satSetters).forEach(setter => setter([]));
      return;
    }

    Object.entries(ATMOS_TYPES).forEach(async ([type, { file, stateKey }]) => {
      const setter = satSetters[stateKey];
      if (!setter) {
        console.error(`No setter found for stateKey="${stateKey}"`);
        return;
      }

      const url = withBase(`data/${model}/${file}`);
      console.log(`Fetching ${type} sats:`, url);

      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(res.statusText);
        setter(await res.json());
      } catch (err) {
        console.error(`Failed to load ${file} for model ${model}`, err);
        setter([]);
      }
    });
  }, [model]);

  useEffect(() => {
    if (!model) {
      Object.values(convSetters).forEach(setter => setter([]));
      return;
    }

    Object.entries(CONVENTIONAL_TYPES).forEach(async ([obsType, { file, stateKey }]) => {
      const setter = convSetters[stateKey];
      if (!setter) {
        console.error(`No setter found for stateKey="${stateKey}"`);
        return;
      }

      const url = withBase(`data/${model}/${file}`);
      console.log(`Fetching ${obsType} types:`, url);

      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(res.statusText);
        setter(await res.json());
      } catch (err) {
        console.error(`Failed to load ${file} for model ${model}`, err);
        setter([]);
      }
    });
  }, [model]);


  useEffect(() => {
    fetch(withBase("data/configIndex.json"))
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! Status: ${res.status}`);
        return res.json();
      })
      .then(data => setConfig(data))
      .catch(err => console.error("Failed to load configIndex.json:", err));
  }, []);

  useEffect(() => {
    if (model) {
      setCycleTime(null);              // immediate UI update
      previousCycle.current = null;    // force refresh
    }
  }, [model]);

  // cycle fetch
  useEffect(() => {
    if (!model) {
      setCycleTime(null);
      previousCycle.current = null;
      return;
    }

    const fetchCycle = async () => {
      try {
        const res = await fetch(
          withBase(`data/${model}/latestCycle.json`),
          { cache: "no-store" }
        );
        const json = await res.json();
        setCycleTime(json.cycleTime ?? null);
        previousCycle.current = json.cycleTime ?? null;
      } catch (error) {
        console.error(`Failed to load latestCycle.json for model ${model}:`, error);
        setCycleTime(null);
        previousCycle.current = null;
      }
    };

    fetchCycle();
    const interval = setInterval(fetchCycle, 300000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") fetchCycle();
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [model]);

  const toggleSection = (name) => {
    setOpenSection(openSection === name ? null : name);
  };

  const toggleSat = (name) => {
    setOpenSat(openSat === name ? null : name);
  };

  const availableComponents =
    model && modelsConfig?.components
      ? modelsConfig.components[model] || []
      : [];

  // --- LAYOUT ---
  return (
    <div className="flex flex-col lg:flex-row min-h-screen">

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-full w-72 bg-blue-100 p-4 border-r overflow-y-auto transform transition-transform duration-300 ease-in-out
    ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} 
    lg:relative lg:translate-x-0 lg:w-64 z-50`}
      >

        <h1 className="text-lg font-bold mb-4 text-center">
          <span className="underline block">Monitoring Dashboard</span>
          {config?.name && (
            <span className="block font-normal text-sm mt-1">{config.name}</span>
          )}
        </h1>

        {/* Model / Component selectors */}
        {modelsConfig && (
          <div className="mb-6 p-3 bg-white rounded shadow-sm">
            <h2 className="font-semibold text-sm mb-2 text-gray-700">
              Model Selection
            </h2>

            {/* Model selector */}
            <label className="block text-xs text-gray-600 mb-1">
              Model
            </label>
            <select
              className="custom-menu-category"
              value={model || ""}
              onChange={(e) => {
                setModel(e.target.value || null);
                setComponent(null); // reset component when model changes
              }}
            >
              <option value="">Select model…</option>
              {modelsConfig.models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>

            {/* Component selector */}
            <label className="block text-xs text-gray-600 mb-1">
              Component
            </label>
            <select
              className='custom-menu-category'
              value={component || ""}
              onChange={(e) => setComponent(e.target.value || null)}
              disabled={!model}
            >
              <option value="">
                {model ? "Select component…" : "Select model first"}
              </option>
              {availableComponents.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            {/* Cycle time */}
            <p className="text-base text-gray-900 font-medium mt-3">
              Cycle: &nbsp;&nbsp; {cycleTime || "Loading..."}
            </p>
          </div>

        )
        }

        {
          geostationarySatellites.length > 0 && (
            <RadianceCategory
              sectionKey="geo"
              label="Geostationary Radiance"
              satelliteList={geostationarySatellites}
              channelMap={{ ABI: ABI.channels, AHI: AHI.channels }}
              openSection={openSection}
              toggleSection={toggleSection}
              openSat={openSat}
              toggleSat={toggleSat}
              navigate={go}
              cycleTime={cycleTime}
              selectedModel={model}
            />
          )
        }

        {
          infraredSatellites.length > 0 && (
            <RadianceCategory
              sectionKey="inf"
              label="Infrared Obs"
              satelliteList={infraredSatellites}
              channelMap={{ CrIS: CrIS.channels, IASI: IASI.channels }}
              openSection={openSection}
              toggleSection={toggleSection}
              openSat={openSat}
              toggleSat={toggleSat}
              navigate={go}
              cycleTime={cycleTime}
              selectedModel={model}
            />
          )
        }

        {
          microwaveSatellites.length > 0 && (
            <RadianceCategory
              sectionKey="mic"
              label="Microwave Observations"
              satelliteList={microwaveSatellites}
              channelMap={{ AMSUA: AMSUA.channels, ATMS: ATMS.channels, MHS: MHS.channels, SSMIS: SSMIS.channels }}
              openSection={openSection}
              toggleSection={toggleSection}
              openSat={openSat}
              toggleSat={toggleSat}
              navigate={go}
              cycleTime={cycleTime}
              selectedModel={model}
            />
          )
        }

        {
          ozoneSatellites.length > 0 && (
            <OzoneObs
              sectionKey="ozn"
              label="Ozone Observations"
              openSection={openSection}
              toggleSection={toggleSection}
              openSat={openSat}
              toggleSat={toggleSat}
              navigate={go}
              ozoneSatellites={ozoneSatellites}
              channelMap={{ OMI: OMI.channels, OMPSNP: OMPSNP.channels, OMPSTC8: OMPSTC8.channels }}
              cycleTime={cycleTime}
              selectedModel={model}
            />
          )
        }

        <ConventionalObs
          model={model}
          obsType="gps"
          typeList={gpsTypes}
          keyProp="gpskey"
          displayLabel="GPS Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={go}
          cycleTime={cycleTime}
        />
        <ConventionalObs
          model={model}
          obsType="ps"
          typeList={psTypes}
          keyProp="pskey"
          displayLabel="PS Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={go}
          cycleTime={cycleTime}
        />
        <ConventionalObs
          model={model}
          obsType="q"
          typeList={qTypes}
          keyProp="qkey"
          displayLabel="Q Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={go}
          cycleTime={cycleTime}
        />
        <ConventionalObs
          model={model}
          obsType="t"
          typeList={tTypes}
          keyProp="tkey"
          displayLabel="T Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={go}
          cycleTime={cycleTime}
        />
        <ConventionalObs
          model={model}
          obsType="uv"
          typeList={uvTypes}
          keyProp="uvkey"
          displayLabel="UV Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={go}
          cycleTime={cycleTime}
        />
      </aside >

      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-25 lg:hidden z-40"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main content area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between bg-white shadow p-4">
          <h1 className="text-xl font-bold text-center lg:text-left">
            Monitoring Dashboard
          </h1>
          {/* Mobile menu button */}
          <button
            className="lg:hidden p-2 rounded hover:bg-gray-100"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <Menu />
          </button>
        </header>

        {/* Content */}
        <section className="flex-1 p-4 min-w-0">
          <MainContent />
        </section>

        {/* Footer */}
        <footer className="bg-gray-100 text-gray-600 text-center p-2">
          © 2025 ObsMon Dashboard
        </footer>
      </main>
    </div >
  );
}

export default App;
