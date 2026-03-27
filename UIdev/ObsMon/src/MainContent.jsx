// src/MainContent.jsx

import { Routes, Route } from "react-router-dom";
import ChannelWrapper from "./components/ChannelWrapper";
import SummaryWrapper from "./components/SummaryWrapper";
import Home from "./components/Home";
import TimeSeriesWrapper from "./components/TimeSeriesWrapper";
import UnifiedWrapper from "./components/ConvWrapper";

function MainContent() {
    return (
        <main className="flex-1 p-4 overflow-y-auto">
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/:type/:satellite/:instrument/summary" element={<SummaryWrapper />} />
                <Route path="/:type/:satellite/:instrument/time" element={<TimeSeriesWrapper />} />
                <Route path="/:type/:satellite/:instrument/:channelNumber" element={<ChannelWrapper />} />

                <Route path="/:type/:key/:plot_type" element={<UnifiedWrapper />} />
                <Route path="/:type/:key" element={<UnifiedWrapper />} />
                {/* Add more routes here as needed */}
            </Routes>
        </main>
    );
}

export default MainContent;
