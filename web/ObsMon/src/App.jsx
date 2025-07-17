import React, { useEffect, useState, useRef, createContent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "./data/channels.js";
import MainContent from "./MainContent.jsx";
import { withBase } from './utils/paths.js';

import RadianceCategory from './components/RadianceCategory.jsx';
import { geostationarySatellites } from "./data/geosats";
import { infraredSatellites } from './data/infrasats.js';
import { microwaveSatellites } from './data/microwavesats.js';
import OzoneObs from './components/OzoneObs.jsx'
import ConventionalObs from './components/ConventionalObs.jsx';

import { gpsTypes } from "./data/gpstypes";
import { psTypes } from "./data/pstypes";
import { qTypes } from "./data/qtypes";
import { tTypes } from "./data/ttypes";
import { uvTypes } from "./data/uvtypes";

function App() {

  const navigate = useNavigate();

  const [openSection, setOpenSection] = useState(null);
  const [openSat, setOpenSat] = useState(null);

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

        <OzoneObs
          openSection={openSection}
          toggleSection={toggleSection}
          openSat={openSat}
          toggleSat={toggleSat}
          navigate={navigate}
          OMI={OMI}
          OMPSNP={OMPSNP}
          OMPSTC8={OMPSTC8}
          cycleTime={cycleTime}
        />

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


