// A Playwright reporter that writes JUnit XML naming each test's source.
//
// Playwright's own JUnit reporter writes a test's name, its class and its
// time. It holds the test's location as well, and it uses that location only
// in the message of a failure. A consumer of the report therefore knows which
// file a suite came from and not which test inside it, so a result binds to
// every test in the file rather than to the one that produced it.
//
// This reporter writes the same report and adds two attributes: `file`, the
// path of the test's source relative to the project root, and `line`, the
// line the test is declared on. It keeps `hostname` on each suite, which
// names the project the records came from.
//
// It uses the public Reporter interface only. It does not extend Playwright's
// own reporter, because that reporter is reached through a path inside the
// package that its authors may change.
//
// Use it from `playwright.config.ts`:
//
//   reporter: [['./elspais-junit-reporter.mjs', { outputFile: 'junit.xml' }]]
//
// And read it with a target that binds by source:
//
//   [[scanning.test.targets]]
//   name        = "e2e"
//   reporter    = "junit"
//   results     = "junit.xml"
//   match       = "source"
//   environment = "suite-hostname"

import fs from 'node:fs';
import path from 'node:path';

function xmlEscape(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function attributes(pairs) {
    return Object.entries(pairs)
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([name, value]) => `${name}="${xmlEscape(value)}"`)
        .join(' ');
}

export default class ElspaisJUnitReporter {
    constructor(options = {}) {
        this._outputFile = options.outputFile || 'junit.xml';
        this._rootDir = process.cwd();
        // One entry for each project, because a test that runs in several
        // projects produces one record in each of them and a reader must be
        // able to tell those records apart.
        this._byProject = new Map();
    }

    onBegin(config) {
        if (config && config.rootDir) this._rootDir = config.rootDir;
    }

    onTestEnd(test, result) {
        // titlePath() is [root, project, file, ...titles].
        const titles = test.titlePath();
        const project = titles[1] || '';
        const file = titles[2] || '';
        const name = titles.slice(3).join(' › ');

        if (!this._byProject.has(project)) this._byProject.set(project, []);
        this._byProject.get(project).push({
            name,
            classname: file,
            // The location of the test itself, which is what lets a reader
            // bind this record to one test rather than to a whole file.
            file: test.location ? path.relative(this._rootDir, test.location.file) : '',
            line: test.location ? test.location.line : undefined,
            time: (result.duration || 0) / 1000,
            status: result.status,
            message: result.error ? result.error.message || '' : '',
        });
    }

    onEnd() {
        const lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<testsuites>'];

        for (const [project, cases] of this._byProject) {
            const failures = cases.filter(
                (c) => c.status === 'failed' || c.status === 'timedOut' || c.status === 'interrupted'
            ).length;
            const skipped = cases.filter((c) => c.status === 'skipped').length;
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
                if (c.status === 'skipped') {
                    lines.push(open + '>');
                    lines.push('      <skipped/>');
                    lines.push('    </testcase>');
                } else if (failures && c.status !== 'passed') {
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

        const target = path.resolve(this._rootDir, this._outputFile);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, lines.join('\n'), 'utf-8');
    }
}
