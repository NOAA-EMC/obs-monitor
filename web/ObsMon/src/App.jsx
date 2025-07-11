import React, { useEffect, useState, useRef, createContent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ABI, AHI, AMSUA, ATMS, CrIS, IASI, MHS, SSMIS, OMI, OMPSNP, OMPSTC8 } from "./data/channels.js";
import MainContent from "./MainContent.jsx";
import GeostationaryRad from './components/GeostationaryRad.jsx';
import InfraredRad from './components/InfraredRad';
import MicrowaveRad from './components/MicrowaveRad.jsx';
import OzoneObs from './components/OzoneObs.jsx'
import GpsObs from './components/GpsObs.jsx';
import PsObs from './components/PsObs.jsx';
import QObs from './components/QObs.jsx';
import TObs from './components/TObs.jsx';
import UvObs from './components/UvObs.jsx';
import { withBase } from './utils/paths.js';

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

        <GeostationaryRad
          openSection={openSection}
          toggleSection={toggleSection}
          openSat={openSat}
          toggleSat={toggleSat}
          navigate={navigate}
          ABI={ABI}
          AHI={AHI}
          cycleTime={cycleTime}
        />

        <InfraredRad
          openSection={openSection}
          toggleSection={toggleSection}
          openSat={openSat}
          toggleSat={toggleSat}
          navigate={navigate}
          CrIS={CrIS}
          IASI={IASI}
          cycleTime={cycleTime}
        />

        <MicrowaveRad
          openSection={openSection}
          toggleSection={toggleSection}
          openSat={openSat}
          toggleSat={toggleSat}
          navigate={navigate}
          AMSUA={AMSUA}
          ATMS={ATMS}
          MHS={MHS}
          SSMIS={SSMIS}
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

        <GpsObs
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <PsObs
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <QObs
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <TObs
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        <UvObs
          openSection={openSection}
          toggleSection={toggleSection}
          navigate={navigate}
          cycleTime={cycleTime}
        />

        {/* Add more sections here */}
      </aside>

      <MainContent />

    </div>
  );
}

export default App;


