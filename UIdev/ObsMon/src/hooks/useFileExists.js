import { useEffect, useState } from "react";
import { withBase } from "../utils/paths.js";

/**
 * Hook to resolve a file path that may contain a * wildcard via checkfile.php glob support.
 * @param {string} pattern - Relative file path, optionally containing *
 * @returns {{ resolvedPath: string|null, notFound: boolean }} -
 *   resolvedPath is the matched path (or the original if no wildcard), null while checking.
 *   notFound is true when the server confirmed no match.
 */
export function useResolveFile(pattern) {
    const [resolvedPath, setResolvedPath] = useState(null);
    const [notFound, setNotFound] = useState(false);

    useEffect(() => {
        if (!pattern) {
            setResolvedPath(null);
            setNotFound(false);
            return;
        }
        setResolvedPath(null);
        setNotFound(false);

        fetch(withBase(`utils/checkfile.php?file=${encodeURIComponent(pattern)}`))
            .then(res => res.text())
            .then(text => {
                const result = text.trim();
                if (result === "false") {
                    setNotFound(true);
                } else if (result === "true") {
                    // Exact match, no wildcard
                    setResolvedPath(pattern);
                } else {
                    // Glob returned a resolved relative path
                    setResolvedPath(result);
                }
            })
            .catch(() => setNotFound(true));
    }, [pattern]);

    return { resolvedPath, notFound };
}

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
