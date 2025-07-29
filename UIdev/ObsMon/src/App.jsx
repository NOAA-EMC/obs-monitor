import React, { useEffect, useState, useRef, createContent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "./data/channels.js";
import MainContent from "./MainContent.jsx";
import { withBase } from './utils/paths.js';

import RadianceCategory from './components/RadianceCategory.jsx';
// import { geostationarySatellites } from "./data/geosats";
// import { infraredSatellites } from './data/infrasats.js';
// import { microwaveSatellites } from './data/microwavesats.js';
import OzoneObs from './components/OzoneObs.jsx'
import ConventionalObs from './components/ConventionalObs.jsx';

function App() {

  const navigate = useNavigate();

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

  const toggleSection = (name) => {
    setOpenSection(openSection === name ? null : name);
  };

  const toggleSat = (name) => {
    setOpenSat(openSat === name ? null : name);
  };

  const [cycleTime, setCycleTime] = useState(null);
  const previousCycle = useRef(null);

  // Load the current cycle and refresh periodically
  useEffect(() => {
    const fetchCycle = async () => {
      try {
        const res = await fetch(withBase('data/currentCycle.json'), { cache: 'no-store' });
        const json = await res.json();
        if (json.cycleTime && json.cycleTime !== previousCycle.cycleTime) {
          setCycleTime(json.cycleTime);
          previousCycle.cycleTime = json.cycleTime;
        }
      } catch (error) {
        console.error('Failed to load current cycle:', error);
      }
    };

    fetchCycle(); // Load on mount

    const interval = setInterval(fetchCycle, 60000); // Poll every 60 seconds

    return () => clearInterval(interval); // Cleanup
  }, []);

  return (


    <div className="flex min-h-screen">
      <aside className="w-64  shrink-0 bg-blue-100 p-4 border-r">
        <h1 className="text-lg font-bold mb-4 underline">Monitoring Dashboard</h1>

        {/* Add current cycle below header */}
        <p className="text-base text-black mb-4">
          Current Cycle: &nbsp; &nbsp; {cycleTime || "Loading..."}
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
            navigate={navigate}
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
            navigate={navigate}
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
            navigate={navigate}
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
            navigate={navigate}
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
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <ConventionalObs
          obsType="ps"
          typeList={psTypes}
          keyProp="pskey"
          displayLabel="PS Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <ConventionalObs
          obsType="q"
          typeList={qTypes}
          keyProp="qkey"
          displayLabel="Q Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <ConventionalObs
          obsType="t"
          typeList={tTypes}
          keyProp="tkey"
          displayLabel="T Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <ConventionalObs
          obsType="uv"
          typeList={uvTypes}
          keyProp="uvkey"
          displayLabel="UV Observations"
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

      </aside>

      <MainContent />

    </div>
  );
}

export default App;


