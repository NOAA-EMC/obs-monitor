import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu } from "lucide-react"; // hamburger icon
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "./data/channels.js";
import MainContent from "./MainContent.jsx";
import { withBase } from './utils/paths.js';

import RadianceCategory from './components/RadianceCategory.jsx';
import OzoneObs from './components/OzoneObs.jsx';
import ConventionalObs from './components/ConventionalObs.jsx';

function App() {
  const navigate = useNavigate();

  const go = (to) => {
    navigate(to);
    if (window.innerWidth < 1024) setSidebarOpen(false); // only close on mobile/tablet
  };

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

  // --- fetch data (unchanged) ---
  useEffect(() => {
    fetch(withBase('data/gpstypes.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setGpsTypes(data))
      .catch(err => console.error("Failed to load gpsTypes:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/pstypes.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setPsTypes(data))
      .catch(err => console.error("Failed to load psTypes:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/qtypes.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setQTypes(data))
      .catch(err => console.error("Failed to load qTypes:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/ttypes.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setTTypes(data))
      .catch(err => console.error("Failed to load tTypes:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/uvtypes.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setUvTypes(data))
      .catch(err => console.error("Failed to load uvTypes:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/ozonesats.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setOzoneSatellites(data))
      .catch(err => console.error("Failed to load ozoneSatellites:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/microwavesats.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setMicrowaveSatellites(data))
      .catch(err => console.error("Failed to load microwaveSatellites:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/infraredsats.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setInfraredSatellites(data))
      .catch(err => console.error("Failed to load infraredSatellites:", err));
  }, []);
  useEffect(() => {
    fetch(withBase('data/geostationarysats.json'), { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setGeostationarySatellites(data))
      .catch(err => console.error("Failed to load geostationarySatellites:", err));
  }, []);
  useEffect(() => {
    fetch(withBase("data/configIndex.json"))
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! Status: ${res.status}`);
        return res.json();
      })
      .then(data => setConfig(data))
      .catch(err => console.error("Failed to load configIndex.json:", err));
  }, []);

  // cycle fetch
  useEffect(() => {
    const fetchCycle = async () => {
      try {
        const res = await fetch(withBase('data/currentCycle.json'), { cache: 'no-store' });
        const json = await res.json();
        if (json.cycleTime && json.cycleTime !== previousCycle.current) {
          setCycleTime(json.cycleTime);
          previousCycle.current = json.cycleTime;
        }
      } catch (error) {
        console.error('Failed to load current cycle:', error);
      }
    };

    fetchCycle();
    const interval = setInterval(fetchCycle, 300000); // 5 min
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') fetchCycle();
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const toggleSection = (name) => {
    setOpenSection(openSection === name ? null : name);
  };

  const toggleSat = (name) => {
    setOpenSat(openSat === name ? null : name);
  };

  // --- LAYOUT ---
  return (
    <div className="flex flex-col lg:flex-row min-h-screen">

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-full w-72 bg-blue-100 p-4 border-r overflow-y-auto transform transition-transform duration-300 ease-in-out
    ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} 
    lg:relative lg:translate-x-0 lg:w-64 z-50`}
      >

        {/* <aside
        className={`fixed top-0 left-0 h-full bg-blue-100 p-4 border-r overflow-y-auto transform transition-transform duration-300 ease-in-out
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} 
          lg:relative lg:translate-x-0 lg:w-64`}
      > */}


        <h1 className="text-lg font-bold mb-4 text-center">
          <span className="underline block">Monitoring Dashboard</span>
          {config?.name && (
            <span className="block font-normal text-sm mt-1">{config.name}</span>
          )}
        </h1>

        <p className="text-base text-black mb-4 text-center">
          Current Cycle: {cycleTime || "Loading..."}
        </p>

        {geostationarySatellites.length > 0 && (
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
          />
        )}

        {infraredSatellites.length > 0 && (
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
          />
        )}

        {microwaveSatellites.length > 0 && (
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
          />
        )}

        {ozoneSatellites.length > 0 && (
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
          />
        )}

        <ConventionalObs
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
          obsType="uv"
          typeList={uvTypes}
          keyProp="uvkey"
          displayLabel="UV Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={go}
          cycleTime={cycleTime}
        />
      </aside>

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
    </div>
  );
}

export default App;
