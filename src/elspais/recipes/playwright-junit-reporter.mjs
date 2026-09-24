// A Playwright reporter that writes JUnit XML naming each test's source.
//
// Playwright's own JUnit reporter writes a test's name, its class and its
// time. It holds the test's location as well, and it uses that location only
// in the message of a failure. A consumer of the report therefore knows which
// file a suite came from and not which test inside it, so a result cannot be
// bound to the one test that produced it.
//
// This reporter writes the same report and adds two attributes: `file`, the
// path of the test's source, and `line`, the line the test is declared on
// (counted from one, as Playwright counts it). It keeps `hostname` on each
// suite, which names the project the records came from.
//
// It writes ONE record for each test in each project, carrying the test's
// outcome as Playwright itself judges it -- not one record for each attempt.
// A test that failed and then passed on a retry is flaky and passed; a test
// marked `test.fail()` that failed is an expected failure and passed. Each
// record is a result of its own to a reader of the report, so writing an
// attempt as a record would report a failure the runner does not.
//
// It uses the public Reporter interface only. It does not extend Playwright's
// own reporter, because that reporter is reached through a path inside the
// package that its authors may change.
//
// Use it from `playwright.config.ts`:
//
//   reporter: [['./elspais-junit-reporter.mjs', { outputFile: 'junit.xml' }]]
//
// `outputFile` is read relative to the directory holding the Playwright
// config, as Playwright's own reporters read it, and so is `file`. Pass
// `rootDir` to write `file` relative to another directory instead (it too is
// read relative to the config's directory).
//
// And read it with a target whose `cwd` is the directory holding the config
// (a relative `file` is read against the target's cwd, and `results` is
// relative to it):
//
//   [[scanning.test.targets]]
//   name        = "e2e"
//   cwd         = "path/to/the/playwright/project"
//   reporter    = "junit"
//   results     = "junit.xml"
//   match       = "source"
//   environment = "suite-hostname"
//   line_base   = 1   # this reporter counts lines from one; junit declares zero
//
// Clear the previous run's report before each run: every record in the
// results file is read as a result of the run.

import fs from 'node:fs';
import path from 'node:path';

// ANSI control sequences, as Playwright's own reporters strip them. An
// `expect()` message carries them whatever FORCE_COLOR says.
const ANSI = new RegExp(
    '[\\u001B\\u009B][[\\]()#;?]*(?:(?:(?:[a-zA-Z\\d]*(?:;[-a-zA-Z\\d\\/#&.:=?%@~_]*)*)?\\u0007)' +
        '|(?:(?:\\d{1,4}(?:;\\d{0,4})*)?[\\dA-PR-TZcf-ntqry=><~]))',
    'g'
);
// Characters XML 1.0 forbids or discourages. One of them in an attribute
// makes the whole document unreadable, and every record in it is lost.
const DISCOURAGED_XML = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u0084\u0086-\u009f]/g;

function xmlEscape(value) {
    return String(value)
        .replace(ANSI, '')
        .replace(DISCOURAGED_XML, '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;');
}

function attributes(pairs) {
    return Object.entries(pairs)
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([name, value]) => `${name}="${xmlEscape(value)}"`)
        .join(' ');
}

// The outcome of a test over all its attempts, as Playwright computes it
// (`test.outcome()`), for a test object that does not offer it.
function outcomeOf(test, results) {
    if (typeof test.outcome === 'function') return test.outcome();
    const expectedStatus = test.expectedStatus || 'passed';
    let skipped = 0;
    let expected = 0;
    let unexpected = 0;
    for (const result of results) {
        if (result.status === 'interrupted') continue;
        if (result.status === 'skipped') {
            if (expectedStatus === 'skipped') skipped++;
        } else if (result.status === expectedStatus) {
            expected++;
        } else {
            unexpected++;
        }
    }
    if (expected === 0 && unexpected === 0) return 'skipped';
    if (unexpected === 0) return 'expected';
    if (expected === 0 && skipped === 0) return 'unexpected';
    return 'flaky';
}

export default class ElspaisJUnitReporter {
    constructor(options = {}) {
        this._options = options;
        this._outputFile = options.outputFile || 'junit.xml';
        this._configDir = process.cwd();
        this._rootDir = process.cwd();
        this._suite = null;
        // Every test seen, in the order first seen, with the attempts it
        // made. One test object is one test in one project.
        this._tests = new Map();
    }

    onBegin(config, suite) {
        // `config.rootDir` is the test directory, not the project, so it is
        // not where a report or a path is read from.
        if (config && config.configFile) this._configDir = path.dirname(config.configFile);
        this._rootDir = this._options.rootDir
            ? path.resolve(this._configDir, this._options.rootDir)
            : this._configDir;
        this._suite = suite || null;
    }

    _entry(test) {
        if (!this._tests.has(test)) this._tests.set(test, []);
        return this._tests.get(test);
    }

    onTestEnd(test, result) {
        // Called once for each attempt; the record is written from all of
        // them at the end.
        this._entry(test).push(result);
    }

    onEnd() {
        // A test that never reached onTestEnd (a run stopped early) is still
        // a test of the run, and reads as Playwright reads it: skipped.
        if (this._suite && typeof this._suite.allTests === 'function') {
            for (const test of this._suite.allTests()) this._entry(test);
        }

        const byProject = new Map();
        for (const [test, results] of this._tests) {
            // titlePath() is [root, project, file, ...titles].
            const titles = test.titlePath();
            const project = titles[1] || '';
            const outcome = outcomeOf(test, results);
            const failing = [...results].reverse().find((r) => r.error);
            if (!byProject.has(project)) byProject.set(project, []);
            byProject.get(project).push({
                name: titles.slice(3).join(' › '),
                classname: titles[2] || '',
                // The location of the test itself, which is what lets a reader
                // bind this record to one test rather than to a whole file.
                file: test.location ? path.relative(this._rootDir, test.location.file) : '',
                line: test.location ? test.location.line : undefined,
                time: results.reduce((total, r) => total + (r.duration || 0), 0) / 1000,
                outcome,
                message: outcome === 'unexpected' && failing ? failing.error.message || '' : '',
            });
        }

        const lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<testsuites>'];

        for (const [project, cases] of byProject) {
            const failures = cases.filter((c) => c.outcome === 'unexpected').length;
            const skipped = cases.filter((c) => c.outcome === 'skipped').length;
            const time = cases.reduce((total, c) => total + c.time, 0);

            lines.push(
                '  <testsuite ' +
                    attributes({
                        name: project || 'playwright',
                        hostname: project,
                        tests: cases.length,
                        failures,
                        skipped,
                        errors: 0,
                        time,
                    }) +
                    '>'
            );

            for (const c of cases) {
                const open =
                    '    <testcase ' +
                    attributes({
                        name: c.name,
                        classname: c.classname,
                        file: c.file,
                        line: c.line,
                        time: c.time,
                    });
                if (c.outcome === 'skipped') {
                    lines.push(open + '>');
                    lines.push('      <skipped/>');
                    lines.push('    </testcase>');
                } else if (c.outcome === 'unexpected') {
                    lines.push(open + '>');
                    lines.push('      <failure ' + attributes({ message: c.message }) + '/>');
                    lines.push('    </testcase>');
                } else {
                    lines.push(open + '/>');
                }
            }

            lines.push('  </testsuite>');
        }

        lines.push('</testsuites>', '');

        const target = path.resolve(this._configDir, this._outputFile);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, lines.join('\n'), 'utf-8');
    }
}
