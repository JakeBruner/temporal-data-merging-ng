'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { run } = require('ormas_acceptance');

// The candidate process loads the delivered component itself. Only framework
// decorators and child-component metadata are isolated; checkDiffs is unchanged.
const candidateJs = String.raw`
  const fs = require('node:fs');
  const vm = require('node:vm');
  const ts = require('typescript');
  const fixture = JSON.parse(process.argv[1]);
  const quietConsole = Object.fromEntries(
    ['log', 'info', 'warn', 'error', 'debug'].map((name) => [name, () => {}])
  );
  const identityDecorator = () => (target, key, descriptor) =>
    key === undefined ? target : descriptor;

  function evaluateTypeScript(filename, resolveImport) {
    const source = fs.readFileSync(filename, 'utf8');
    const compiled = ts.transpileModule(source, {
      fileName: filename,
      reportDiagnostics: true,
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.CommonJS,
        experimentalDecorators: true,
        useDefineForClassFields: false,
        importHelpers: false
      }
    });
    const errors = (compiled.diagnostics || []).filter(
      (diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error
    );
    if (errors.length) {
      throw new Error(errors.map((diagnostic) =>
        ts.flattenDiagnosticMessageText(diagnostic.messageText, ' ')
      ).join('; '));
    }
    const candidateModule = { exports: {} };
    vm.runInNewContext(compiled.outputText, {
      module: candidateModule,
      exports: candidateModule.exports,
      require: resolveImport,
      Date,
      console: quietConsole
    }, { filename, timeout: 5000 });
    return candidateModule.exports;
  }

  const model = evaluateTypeScript(
    'src/app/timeline/date-range.model.ts',
    (name) => { throw new Error('Unexpected model import: ' + name); }
  );
  const imports = {
    '@angular/core': {
      Component: identityDecorator,
      ViewChild: identityDecorator,
      HostListener: identityDecorator,
      ElementRef: class ElementRef {}
    },
    '@angular/common': { CommonModule: class CommonModule {} },
    './date-range.model': model,
    './entry-form/entry-form.component': {
      EntryFormComponent: class EntryFormComponent {}
    },
    './conflict-resolution/conflict-resolution.component': {
      ConflictResolutionComponent: class ConflictResolutionComponent {}
    },
    './update-card/update-card.component': {
      UpdateCardComponent: class UpdateCardComponent {}
    }
  };
  const { TimelineComponent } = evaluateTypeScript(
    'src/app/timeline/timeline.component.ts',
    (name) => {
      if (!Object.hasOwn(imports, name)) {
        throw new Error('Unexpected component import: ' + name);
      }
      return imports[name];
    }
  );

  function hydrate(entry) {
    return {
      id: entry.id,
      expectedLoss: entry.expectedLoss,
      dateRange: new model.DateRange(
        new Date(entry.start), new Date(entry.end)
      )
    };
  }

  function serialize(entries) {
    return Array.from(entries, (entry) => ({
      id: entry.id,
      expectedLoss: entry.expectedLoss,
      start: entry.dateRange.start.toISOString(),
      end: entry.dateRange.end.toISOString()
    })).sort((a, b) => a.id - b.id);
  }

  const component = new TimelineComponent();
  component.unmodifiedTimelineData = fixture.original.map(hydrate);
  const snapshots = [];
  for (const revision of fixture.revisions) {
    component.timelineData = revision.map(hydrate);
    component.checkDiffs();
    const additions = serialize(component.stagedAdditions);
    const deletions = serialize(component.stagedDeletions);
    const updates = serialize(component.stagedUpdates);
    snapshots.push({
      additionIds: additions.map((entry) => entry.id),
      deletionIds: deletions.map((entry) => entry.id),
      updateIds: updates.map((entry) => entry.id),
      additions,
      deletions,
      updates,
      changesStaged: component.changesStaged()
    });
  }
  process.stdout.write(JSON.stringify(snapshots));
`;

const start = '2024-01-01T00:00:00.000Z';
const end = '2024-02-01T00:00:00.000Z';
const laterStart = '2024-01-05T00:00:00.000Z';
const laterEnd = '2024-03-01T00:00:00.000Z';

function entry(id, rangeStart = start, rangeEnd = end, expectedLoss = 10) {
  return { id, expectedLoss, start: rangeStart, end: rangeEnd };
}

// Expectations name the intended records explicitly instead of duplicating
// the component's ID-difference algorithm in the acceptance driver.
function expected({ additions = [], deletions = [], updates = [] } = {}) {
  const ordered = (entries) => entries.slice().sort((a, b) => a.id - b.id);
  const added = ordered(additions);
  const deleted = ordered(deletions);
  const updated = ordered(updates);
  return {
    additionIds: added.map((record) => record.id),
    deletionIds: deleted.map((record) => record.id),
    updateIds: updated.map((record) => record.id),
    additions: added,
    deletions: deleted,
    updates: updated,
    changesStaged: added.length + deleted.length + updated.length > 0
  };
}

async function observe(original, revisions) {
  const observed = await run([
    'node', '-e', candidateJs, JSON.stringify({ original, revisions })
  ], 30);
  assert.equal(observed.returncode, 0, observed.output);
  let snapshots;
  assert.doesNotThrow(() => {
    snapshots = JSON.parse(observed.output);
  }, 'Candidate must return only the logical JSON snapshots');
  return snapshots;
}

test('empty original and current timelines stage no changes', async () => {
  assert.deepEqual(await observe([], [[]]), [expected()]);
});

test('unchanged populated timelines stage no changes', async () => {
  const original = [entry(1), entry(2, laterStart, laterEnd, 0)];
  assert.deepEqual(await observe(original, [original]), [expected()]);
});

test('equal-count replacement stages both the new and removed records', async () => {
  const removed = entry(2, laterStart, laterEnd, 42);
  const added = entry(-1, start, laterEnd, 0);
  assert.deepEqual(
    await observe([entry(1), removed], [[entry(1), added]]),
    [expected({ additions: [added], deletions: [removed] })]
  );
});

test('a net-growing timeline still stages its simultaneous deletion', async () => {
  const removed = entry(2, laterStart, laterEnd, 25);
  const firstAdded = entry(-1, start, laterEnd, 0);
  const secondAdded = entry(-2, laterStart, end, 15);
  assert.deepEqual(
    await observe([entry(1), removed], [[entry(1), firstAdded, secondAdded]]),
    [expected({ additions: [firstAdded, secondAdded], deletions: [removed] })]
  );
});

test('a net-shrinking timeline still stages its simultaneous addition', async () => {
  const firstRemoved = entry(2, laterStart, laterEnd, 25);
  const secondRemoved = entry(3, start, laterEnd, 30);
  const added = entry(-1, laterStart, end, 0);
  assert.deepEqual(
    await observe([entry(1), firstRemoved, secondRemoved], [[entry(1), added]]),
    [expected({ additions: [added], deletions: [firstRemoved, secondRemoved] })]
  );
});

test('removing an added record clears stale staged additions', async () => {
  const original = [entry(1)];
  const added = entry(-1, laterStart, laterEnd, 0);
  assert.deepEqual(
    await observe(original, [[entry(1), added], original]),
    [expected({ additions: [added] }), expected()]
  );
});

test('restoring a removed record clears stale staged deletions', async () => {
  const removed = entry(2, laterStart, laterEnd, 25);
  const original = [entry(1), removed];
  assert.deepEqual(
    await observe(original, [[entry(1)], original]),
    [expected({ deletions: [removed] }), expected()]
  );
});

test('adding to an empty original then reverting clears all staging', async () => {
  const added = entry(-1, laterStart, laterEnd, 0);
  assert.deepEqual(
    await observe([], [[added], []]),
    [expected({ additions: [added] }), expected()]
  );
});

test('removing every original record stages each deletion with its original data', async () => {
  const original = [entry(1), entry(2, laterStart, laterEnd, 0)];
  assert.deepEqual(
    await observe(original, [[]]),
    [expected({ deletions: original })]
  );
});

test('a start-date update is staged and clears after restoring the original dates', async () => {
  const original = [entry(1), entry(2, laterStart, laterEnd, 25)];
  const changed = entry(1, laterStart, end);
  assert.deepEqual(
    await observe(original, [[changed, original[1]], original]),
    [expected({ updates: [changed] }), expected()]
  );
});

test('an end-date-only update retains the current changed date in its staged record', async () => {
  const changed = entry(1, start, laterEnd, 0);
  assert.deepEqual(
    await observe([entry(1, start, end, 0)], [[changed]]),
    [expected({ updates: [changed] })]
  );
});

test('one revision independently stages a date update, addition, and deletion', async () => {
  const removed = entry(2, laterStart, laterEnd, 25);
  const changed = entry(1, laterStart, laterEnd);
  const added = entry(-1, start, end, 0);
  assert.deepEqual(
    await observe([entry(1), removed], [[changed, added]]),
    [expected({ additions: [added], deletions: [removed], updates: [changed] })]
  );
});
