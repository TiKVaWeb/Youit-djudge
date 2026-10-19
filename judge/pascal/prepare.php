<?php declare(strict_types=1);

/** Prepare an auto-detected Pascal executable inside DOMjudge's build sandbox. */
function preparePascalExecutable(string $directory, string $type): string
{
    $programs = [];
    $testlib = null;
    foreach (scandir($directory) as $file) {
        $path = $directory . '/' . $file;
        if (!is_file($path) || !in_array(strtolower(pathinfo($file, PATHINFO_EXTENSION)), ['dpr', 'pas', 'pp'], true)) {
            continue;
        }
        $source = file_get_contents($path);
        if ($source === false) {
            throw new RuntimeException('Cannot read Pascal source: ' . $file);
        }
        // Ignore comments/directives when distinguishing units from programs.
        $code = preg_replace('/\{[^}]*\}|\(\*.*?\*\)|\/\/[^\r\n]*/s', '', $source);
        $code = ltrim($code ?? '', "\xEF\xBB\xBF \t\r\n");
        if (preg_match('/^unit\s+/i', $code)) {
            if (preg_match('/^unit\s+testlib\s*;/i', $code)) {
                $testlib = $file;
            }
            continue;
        }
        $programs[$file] = $code;
    }
    if (count($programs) !== 1) {
        throw new RuntimeException('Pascal executable requires exactly one program; provide an explicit build script for multiple programs.');
    }
    $filename = array_key_first($programs);
    $usesTestlib = $type === 'compare' && preg_match('/\buses\s+[^;]*\btestlib\b/i', $programs[$filename]);
    $binary = 'run';
    if ($usesTestlib) {
        if ($testlib === null && !copy(__DIR__ . '/vendor/testlib.pas', $directory . '/testlib.pas')) {
            throw new RuntimeException('Cannot install Pascal testlib support.');
        }
        if (!copy(__DIR__ . '/run-testlib', $directory . '/.domjudge-pascal-run')) {
            throw new RuntimeException('Cannot install Pascal checker protocol adapter.');
        }
        $binary = 'checker.bin';
    }
    $build = "#!/bin/sh\nset -eu\nfpc -Mdelphi -O2 -Fu. -o" . $binary . ' ' . escapeshellarg($filename) . "\n";
    if ($usesTestlib) {
        $build .= "cp .domjudge-pascal-run run\nchmod +x run\n";
    }
    return $build;
}
