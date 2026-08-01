// Check the search against a real index built by gen_search_maildir.py.
//
// Run with:  rake search_test
//
// index.js exports its search functions when loaded outside a browser, so this
// runs the code the page runs, against the files the page loads.

const fs = require('fs');
const path = require('path');

const { tokenize, searchIds, searchNotes } = require(
    path.join(__dirname, '..', 'haildir', 'assets', 'index.js'));

const out = process.argv[2];
const searchIndex = JSON.parse(fs.readFileSync(path.join(out, 'search_index.json')));
const idMapping = JSON.parse(fs.readFileSync(path.join(out, 'id_mapping.json')));
const indexData = JSON.parse(fs.readFileSync(path.join(out, 'index.json')));

function search(term) {
    const result = searchIds(term, searchIndex);
    const emails = result.ids === null
        ? indexData
        : indexData.filter(email => result.ids.has(idMapping[email.id]));
    return {
        count: emails.length,
        subjects: emails.map(email => email.subject),
        notes: searchNotes(result),
    };
}

let failures = 0;

function check(name, got, want) {
    const ok = JSON.stringify(got) === JSON.stringify(want);
    if (!ok) {
        failures++;
        console.log(`FAIL ${name}\n       got  ${JSON.stringify(got)}\n       want ${JSON.stringify(want)}`);
    } else {
        console.log(`ok   ${name}`);
    }
}

const total = indexData.length;

check('a query is split the way the indexer splits an address',
      tokenize('deep.thought@hitchhiker.example'),
      ['deep', 'thought', 'hitchhiker', 'example']);

// This is what was broken: posting lists hold email indexes, and id_mapping.json
// maps a Message-ID to one, so it has to be applied in that direction.
check('a word finds the emails holding it', search('alpha').count, 3);

check('two words match emails holding both, not either',
      search('alpha bravo').subjects, ['Both']);

check('an address in a body is searchable',
      search('deep.thought@hitchhiker.example').subjects, ['Answer']);

check('a word no email holds matches nothing', search('zzzznotaword').count, 0);
check('a word no email holds is reported',
      search('zzzznotaword').notes, 'No email contains "zzzznotaword".');

// A word over --max-postings is stored as an empty list. It cannot narrow
// anything, so it is ignored and said to be ignored, not treated as unmatched.
check('a word too common to index does not empty the results',
      search('newsletter').count, total);
check('a word too common to index is reported',
      search('newsletter').notes,
      '"newsletter" is too common to be indexed, so it was ignored.');
check('a word too common to index does not cancel a real one',
      search('newsletter alpha').count, 3);

check('an empty query constrains nothing', search('').count, total);
check('a query of only punctuation constrains nothing', search('---').count, total);

console.log(failures ? `\n${failures} failed` : '\nAll search checks passed.');
process.exit(failures ? 1 : 0);
