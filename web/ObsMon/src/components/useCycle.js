// src/hooks/useCycle.js
import { useEffect, useState } from "react";
import { withBase } from "../utils/paths";

export function useCycle() {
    const [cycle, setCycle] = useState("");

    useEffect(() => {
        fetch(withBase("/data/currentCycle.json"))
            .then(res => res.json())
            .then(config => {
                if (config.cycleTime) {
                    setCycle(config.cycleTime);
                } else {
                    console.error("cycleTime not found in config.json");
                }
            })
            .catch((err) => {
                console.error("Failed to load config.json:", err);
            });
    }, []);

    return cycle;
}
