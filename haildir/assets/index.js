// Load index data
let indexData = [];
let addresses = [];
let searchIndex = {};
let idMapping = {};

// Set once every index has loaded; searching before that would quietly report
// no results because searchIndex is still empty.
let dataReady = false;

// Create a map for quick lookup of email metadata by ID
let emailMap = new Map();

// DOM elements
let emailList, searchInput, searchButton, fromFilter, toFilter;
let dateStart, dateEnd, hasAttachment, searchStatus;

// Split a search box entry the same way the indexer split the emails. The two
// have to agree: `deep.thought@example.com` is stored as four separate words,
// so splitting the query on whitespace alone would look up one long key that is
// never in the index and report no results.
function tokenize(text) {
    return text.toLowerCase().match(/[a-z0-9]+/g) || [];
}

// Look a query up in the inverted index.
//
// Returns the set of email indexes matching *every* word, along with the words
// that could not be used. `ids` is null when the query places no constraint at
// all, which is not the same as matching nothing.
//
// A word maps to an empty posting list when the build found it in more emails
// than --max-postings allows, so its real list was never written. Such a word
// cannot narrow anything and is reported rather than silently treated as a word
// that matches nothing.
function searchIds(term, index) {
    const words = tokenize(term);
    const dropped = [];
    const unknown = [];
    let matched = null;

    for (const word of words) {
        const posting = index[word];

        if (posting === undefined) {
            // No email holds this word, so nothing can hold all of them
            unknown.push(word);
            matched = new Set();
            continue;
        }

        if (posting.length === 0) {
            dropped.push(word);
            continue;
        }

        if (matched === null) {
            matched = new Set(posting);
        } else {
            matched = new Set(posting.filter(id => matched.has(id)));
        }
    }

    return { words, dropped, unknown, ids: matched };
}

// Describe anything the query asked for that the index could not answer, so a
// short result list is not mistaken for a complete one.
function searchNotes(result) {
    const notes = [];
    if (result.unknown.length > 0) {
        notes.push(`No email contains ${result.unknown.map(w => `"${w}"`).join(', ')}.`);
    }
    if (result.dropped.length > 0) {
        notes.push(
            `${result.dropped.map(w => `"${w}"`).join(', ')} ` +
            `${result.dropped.length === 1 ? 'is' : 'are'} too common to be indexed, ` +
            `so ${result.dropped.length === 1 ? 'it was' : 'they were'} ignored.`
        );
    }
    return notes.join(' ');
}

// Node can load this file to exercise the search without a browser; nothing
// below this point runs there (see the guard on the DOMContentLoaded hook).
const inBrowser = typeof document !== 'undefined';
if (!inBrowser && typeof module !== 'undefined' && module.exports) {
    module.exports = { tokenize, searchIds, searchNotes };
}

function setStatus(message, busy) {
    if (!searchStatus) return;
    searchStatus.textContent = message;
    searchStatus.hidden = !message;
    searchStatus.classList.toggle('busy', Boolean(busy));
}

// Give the browser a chance to actually paint the status before the main thread
// is tied up. requestAnimationFrame fires *before* the paint, so it takes two.
function painted() {
    return new Promise(resolve => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
    });
}

async function loadJson(url, label) {
    setStatus(`Loading ${label}…`, true);
    await painted();
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Could not load ${url}: ${response.status}`);
    }
    return response.json();
}

// Load data on page load
if (inBrowser) document.addEventListener('DOMContentLoaded', async () => {
    emailList = document.getElementById('email-list');
    searchInput = document.getElementById('search-input');
    searchButton = document.getElementById('search-button');
    fromFilter = document.getElementById('from-filter');
    toFilter = document.getElementById('to-filter');
    dateStart = document.getElementById('date-start');
    dateEnd = document.getElementById('date-end');
    hasAttachment = document.getElementById('has-attachment');
    searchStatus = document.getElementById('search-status');

    searchButton.addEventListener('click', runSearch);
    searchInput.addEventListener('keyup', (e) => {
        if (e.key === 'Enter') {
            runSearch();
        }
    });

    try {
        // Load main index
        indexData = await loadJson('index.json', 'email list');

        // Create email map for quick lookup
        indexData.forEach(email => {
            emailMap.set(email.id, email);
        });

        // The largest file by far, so it gets its own message
        searchIndex = await loadJson('search_index.json', 'search index');

        idMapping = await loadJson('id_mapping.json', 'message ids');
        addresses = await loadJson('addresses.json', 'addresses');

        // Initialize autocomplete
        initAutocomplete();

        dataReady = true;
        setStatus('', false);

        // Display all emails initially
        displayEmails(indexData);
    } catch (error) {
        console.error('Error loading data:', error);
        setStatus(`Error loading email data: ${error.message}`, false);
        emailList.innerHTML = '<li>Error loading email data</li>';
    }
});

// Sort emails by date (newest first)
function sortEmailsByDate(emails) {
    return emails.slice().sort((a, b) => {
        // Convert date strings to Date objects for comparison
        const dateA = a.date ? new Date(a.date) : new Date(0);  // Use epoch date for missing dates
        const dateB = b.date ? new Date(b.date) : new Date(0);

        // Compare dates in descending order (newest first)
        // If either date is invalid, put it at the end
        if (isNaN(dateA.getTime())) return 1;
        if (isNaN(dateB.getTime())) return -1;

        if (dateB > dateA) return 1;
        if (dateB < dateA) return -1;
        return 0;
    });
}

// Implement pagination with show more button
let currentEmails = [];
let displayedCount = 0;
const batchSize = 100;  // Changed from 500 to 100 as requested
let showMoreButton = null;

// Display emails in the list with show more button
function displayEmails(emails) {
    // Store all emails for potential future display
    currentEmails = sortEmailsByDate(emails);
    displayedCount = 0;

    // Update results count
    updateResultsCount(currentEmails.length);

    if (currentEmails.length === 0) {
        emailList.innerHTML = '<li>No emails found</li>';
        // Hide the show more button if there are no results
        document.getElementById('show-more-container').style.display = 'none';
        return;
    }

    // Clear the email list
    emailList.innerHTML = '';

    // Display first batch of emails
    showNextBatch();

    // Get the show more button and attach event listener
    if (!showMoreButton) {
        showMoreButton = document.getElementById('show-more-button');
        showMoreButton.addEventListener('click', showNextBatch);
    }

    // Show or hide the show more button based on whether there are more emails to display
    updateShowMoreButtonVisibility();
}

function updateResultsCount(count) {
    const resultsCountElement = document.getElementById('results-count');
    if (resultsCountElement) {
        if (count === 0) {
            resultsCountElement.textContent = 'No emails found';
        } else if (count === 1) {
            resultsCountElement.textContent = '1 email found';
        } else {
            resultsCountElement.textContent = `${count} emails found`;
        }
    }
}

function showNextBatch() {
    const start = displayedCount;
    const end = Math.min(start + batchSize, currentEmails.length);

    const batch = currentEmails.slice(start, end);

    const batchHTML = batch.map(email => {
        // Format attachment information
        let attachmentInfo = '';
        if (email.has_attachments && email.attachments && email.attachments.length > 0) {
            // Show up to 3 attachment names
            const attachmentNames = email.attachments.slice(0, 3).map(escapeHtml).join(', ');
            const moreCount = email.attachments.length > 3 ? ` and ${email.attachments.length - 3} more` : '';
            attachmentInfo = `<div class="email-attachments">📎 ${attachmentNames}${moreCount}</div>`;
        } else if (email.has_attachments) {
            attachmentInfo = '<div class="email-attachments">📎 Attachment</div>';
        }

        // Add class for emails from me
        const fromMeClass = email.from_me ? ' from-me' : '';

        return `
            <li class="email-item${fromMeClass}" data-id="${email.id}" data-idx="${idMapping[email.id]}">
                <div class="email-subject">${escapeHtml(email.subject)}</div>
                <div class="email-from">From: ${escapeHtml(email.from)}</div>
                <div class="email-date">${formatDate(email.date)}</div>
                <div class="email-preview">${escapeHtml(email.preview)}</div>
                ${attachmentInfo}
            </li>
        `;
    }).join('');

    emailList.insertAdjacentHTML('beforeend', batchHTML);

    // Add click handlers to new email items
    const newItems = emailList.querySelectorAll(`.email-item:not([data-handled])`);
    newItems.forEach(item => {
        item.setAttribute('data-handled', 'true');
        item.addEventListener('click', () => {
            const emailIndex = item.getAttribute('data-idx');
            if (emailIndex !== null) {
                // Pass the index number as the ID for the file lookup
                window.location.href = `email.html?id=${emailIndex}`;
            } else {
                console.error('Email index not found for item');
            }
        });
    });

    displayedCount = end;

    // Update visibility of show more button
    updateShowMoreButtonVisibility();
}

function updateShowMoreButtonVisibility() {
    const showMoreContainer = document.getElementById('show-more-container');
    if (displayedCount >= currentEmails.length) {
        // Hide the button if all emails are displayed
        showMoreContainer.style.display = 'none';
    } else {
        // Show the button if there are more emails to display
        showMoreContainer.style.display = 'block';
    }
}

// Format date for display
function formatDate(dateString) {
    if (!dateString) return 'Unknown date';
    // The backend now provides date in YYYY-MM-DD HH:mm format, so return as is
    return dateString;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    // Convert arrays to strings if needed
    if (Array.isArray(text)) {
        text = text.join(', ');
    }

    if (typeof text !== 'string') {
        text = String(text || '');
    }

    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Filter emails by various criteria. Returns the notes describing anything the
// search index could not answer.
function filterEmails() {
    const searchTerm = searchInput.value.trim();
    const fromTerm = fromFilter.value.toLowerCase();
    const toTerm = toFilter.value.toLowerCase();
    const startDate = dateStart.value;
    const endDate = dateEnd.value;
    const hasAttachmentFilter = hasAttachment.checked;

    let filtered = indexData;
    let notes = '';

    if (searchTerm) {
        const result = searchIds(searchTerm, searchIndex);
        notes = searchNotes(result);
        if (result.ids !== null) {
            // The posting lists hold the index of each email, which is what
            // id_mapping.json maps a Message-ID to.
            filtered = indexData.filter(email => result.ids.has(idMapping[email.id]));
        }
    }

    // Apply additional filters
    filtered = filtered.filter(email => {
        // From filter
        if (fromTerm) {
            // Ensure email.from is a string for comparison
            const fromAddress = email.from ? email.from.toString() : '';
            if (!fromAddress.toLowerCase().includes(fromTerm)) {
                return false;
            }
        }

        // To filter
        if (toTerm) {
            // email.to is an array, check if any address in the array contains the search term
            const toAddresses = Array.isArray(email.to) ? email.to : [email.to];
            const hasMatchingTo = toAddresses.some(addr => addr && addr.toLowerCase().includes(toTerm));
            if (!hasMatchingTo) {
                return false;
            }
        }

        // Date range filter
        if (startDate && email.date < startDate) {
            return false;
        }

        if (endDate && email.date > endDate) {
            return false;
        }

        // Attachment filter
        if (hasAttachmentFilter && !email.has_attachments) {
            return false;
        }

        return true;
    });

    displayEmails(filtered);
    return notes;
}

// Search runs on the main thread and can take a while over a large archive, so
// the status is put up and painted before the work starts.
async function runSearch() {
    if (!dataReady) {
        setStatus('Still loading the archive…', true);
        return;
    }

    setStatus('Searching…', true);
    searchButton.disabled = true;
    await painted();

    try {
        setStatus(filterEmails(), false);
    } catch (error) {
        console.error('Error searching:', error);
        setStatus(`Error searching: ${error.message}`, false);
    } finally {
        searchButton.disabled = false;
    }
}

// Initialize autocomplete for address fields using datalist
function initAutocomplete() {
    // Populate the datalist with email addresses
    const datalist = document.getElementById('email-datalist');

    // Clear existing options
    datalist.innerHTML = '';

    // Add each address as an option
    addresses.forEach(address => {
        const option = document.createElement('option');
        option.value = address;
        datalist.appendChild(option);
    });
}
