<?php declare(strict_types=1);

require __DIR__ . '/prepare.php';

function check(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

function execute(array $command, string $directory, string $stdin = ''): array
{
    $process = proc_open($command, [['pipe', 'r'], ['pipe', 'w'], ['pipe', 'w']], $pipes, $directory);
    check(is_resource($process), 'Cannot start test command');
    fwrite($pipes[0], $stdin);
    fclose($pipes[0]);
    $output = stream_get_contents($pipes[1]) . stream_get_contents($pipes[2]);
    fclose($pipes[1]);
    fclose($pipes[2]);
    return [proc_close($process), $output];
}

$root = sys_get_temp_dir() . '/pascal-tests-' . bin2hex(random_bytes(8));
mkdir($root, 0700);
$source = <<<'PAS'
uses testlib;
var participant, jury: longint;
begin
  participant := ouf.ReadLongint;
  jury := ans.ReadLongint;
  if jury = -999 then quit(_fail, 'broken jury data');
  if participant <> jury then quit(_wa, 'different values');
  quit(_ok, 'same value');
end.
PAS;
$assertions = 0;
foreach (['check.dpr', 'check.pas', 'CHECK.PP', "check ' quoted.dpr"] as $filename) {
    $directory = $root . '/' . (++$assertions);
    mkdir($directory, 0700);
    mkdir($directory . '/feedback', 0700);
    file_put_contents($directory . '/' . $filename, $source);
    // A unit may sort before the main program and must not be picked as entrypoint.
    file_put_contents($directory . '/a_unit.pas', 'unit a_unit; interface implementation end.');
    file_put_contents($directory . '/build', preparePascalExecutable($directory, 'compare'));
    [$status, $output] = execute(['/bin/sh', 'build'], $directory);
    check($status === 0, 'Compile failed: ' . $output);
    file_put_contents($directory . '/input', "1\n");
    chmod($directory . '/input', 0444);
    foreach ([['7', "7\n", 42], ['7', "8\n", 43], ['7', '', 43], ['7', "7 extra\n", 43], ['-999', "7\n", 1]] as [$jury, $answer, $expected]) {
        if (file_exists($directory . '/answer')) {
            chmod($directory . '/answer', 0600);
        }
        file_put_contents($directory . '/answer', $jury . "\n");
        chmod($directory . '/answer', 0444);
        [$status, $output] = execute([$directory . '/run', $directory . '/input', $directory . '/answer', $directory . '/feedback'], '/', $answer);
        check($status === $expected, $filename . ': expected ' . $expected . ', got ' . $status . ': ' . $output);
        check(glob($directory . '/feedback/.pascal-output.*') === [], 'Temporary answer was not removed');
        if ($expected === 1) {
            check(str_contains(file_get_contents($directory . '/feedback/judgeerror.txt'), 'broken jury data'), 'Checker failure lost');
        }
        ++$assertions;
    }
    // An explicitly packaged testlib must not be overwritten on the next build.
    $library = file_get_contents($directory . '/testlib.pas');
    preparePascalExecutable($directory, 'compare');
    check(file_get_contents($directory . '/testlib.pas') === $library, 'Packaged unit overwritten');
    file_put_contents($directory . '/second.dpr', $source);
    try {
        preparePascalExecutable($directory, 'compare');
        throw new LogicException('Ambiguous Pascal programs accepted');
    } catch (RuntimeException $error) {
        check(str_contains($error->getMessage(), 'exactly one'), 'Unexpected ambiguity error');
    }
}
$native = $root . '/native';
mkdir($native, 0700);
file_put_contents($native . '/native.pas', 'begin halt(42); end.');
file_put_contents($native . '/build', preparePascalExecutable($native, 'compare'));
[$status, $output] = execute(['/bin/sh', 'build'], $native);
check($status === 0, 'Native Pascal compile failed: ' . $output);
[$status] = execute([$native . '/run'], '/');
check($status === 42, 'Native Pascal protocol was wrapped unexpectedly');
echo 'PASS: Pascal compilation, protocol verdicts, unit selection, quoting, failure handling, cleanup, native protocol (' . $assertions . " cases)\n";
echo 'Fixtures: ' . $root . "\n";
