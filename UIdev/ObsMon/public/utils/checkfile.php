<?php
// Enable error reporting for debugging (disable in production)
ini_set('display_errors', 1);
error_reporting(E_ALL);

// Set the base directory to the deployment root (adjust as needed)
$baseDir = realpath(__DIR__ . '/..');  // One level up from utils/

// Get the requested file path from the query parameter
$relativePath = isset($_GET['file']) ? $_GET['file'] : '';

// Normalize the path to prevent directory traversal
$fullPath = realpath($baseDir . DIRECTORY_SEPARATOR . $relativePath);

// Check that the resolved path is inside the base directory
if ($fullPath && strpos($fullPath, $baseDir) === 0 && is_file($fullPath)) {
    echo "true";
} else {
    echo "false";
}
?>
