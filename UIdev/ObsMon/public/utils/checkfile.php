<?php
// Enable error reporting for debugging (disable in production)
ini_set('display_errors', 1);
error_reporting(E_ALL);

// Set the base directory to the deployment root (adjust as needed)
$baseDir = realpath(__DIR__ . '/..');  // One level up from utils/

// Get the requested file path from the query parameter
$relativePath = isset($_GET['file']) ? $_GET['file'] : '';

if (strpos($relativePath, '*') !== false) {
    // Glob pattern: build the pattern path and search
    $pattern = $baseDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relativePath);
    $matches = glob($pattern);
    if ($matches && count($matches) > 0) {
        // Return the relative path of the first match so the client can use it
        $resolved = str_replace($baseDir . DIRECTORY_SEPARATOR, '', $matches[0]);
        echo str_replace(DIRECTORY_SEPARATOR, '/', $resolved);
    } else {
        echo "false";
    }
} else {
    // Exact path: normalize and check
    $fullPath = realpath($baseDir . DIRECTORY_SEPARATOR . $relativePath);
    if ($fullPath && strpos($fullPath, $baseDir) === 0 && is_file($fullPath)) {
        echo "true";
    } else {
        echo "false";
    }
}
?>
