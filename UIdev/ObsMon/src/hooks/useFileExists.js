import { useEffect, useState } from "react";
import { withBase } from "../utils/paths.js";

/**
 * Hook to check if a file exists via checkfile.php
 * @param {string} file - Relative file path to check
 * @returns {boolean|null} - true/false if checked, null if still checking
 */
export function useFileExists(file) {
    const [fileExists, setFileExists] = useState(null);

    useEffect(() => {
        if (!file) {
            setFileExists(null);
            return;
        }

        fetch(withBase(`utils/checkfile.php?file=${encodeURIComponent(file)}`))
            .then(res => res.text())
            .then(text => {
                setFileExists(text.trim() === "true");
            })
            .catch(() => {
                setFileExists(false);
            });
    }, [file]);

    return fileExists;
}
