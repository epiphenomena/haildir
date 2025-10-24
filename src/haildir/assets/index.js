// Load index data
let indexData = [];
let addresses = [];
let searchIndex = {};
let idMapping = {};

// Create a map for quick lookup of email metadata by ID
let emailMap = new Map();

// DOM elements
const emailList = document.getElementById('email-list');
const searchInput = document.getElementById('search-input');
const searchButton = document.getElementById('search-button');
const fromFilter = document.getElementById('from-filter');
const toFilter = document.getElementById('to-filter');
const dateStart = document.getElementById('date-start');
const dateEnd = document.getElementById('date-end');

// Load data on page load
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Load main index
        const indexResponse = await fetch('index.json');
        indexData = await indexResponse.json();
        
        // Create email map for quick lookup
        indexData.forEach(email => {
            emailMap.set(email.id, email);
        });
        
        // Load search index
        const searchIndexResponse = await fetch('search_index.json');
        searchIndex = await searchIndexResponse.json();
        
        // Load ID mapping
        const idMappingResponse = await fetch('id_mapping.json');
        idMapping = await idMappingResponse.json();
        
        // Load addresses for autocomplete
        const addressesResponse = await fetch('addresses.json');
        addresses = await addressesResponse.json();
        
        // Initialize autocomplete
        initAutocomplete();
        
        // Display all emails initially
        displayEmails(indexData);
    } catch (error) {
        console.error('Error loading data:', error);
        emailList.innerHTML = '<li>Error loading email data</li>';
    }
});

// Sort emails by date (newest first)
function sortEmailsByDate(emails) {
    return emails.sort((a, b) => {
        // Convert date strings to Date objects for comparison
        const dateA = new Date(a.date);
        const dateB = new Date(b.date);
        
        // Compare dates in descending order (newest first)
        if (dateB > dateA) return 1;
        if (dateB < dateA) return -1;
        return 0;
    });
}

// Implement virtual scrolling for large email lists
let currentEmails = [];
let displayedCount = 0;
const batchSize = 500;

// Display emails in the list with virtual scrolling
function displayEmails(emails) {
    // Store all emails for potential future display
    currentEmails = sortEmailsByDate(emails);
    displayedCount = 0;
    
    // Update results count
    updateResultsCount(currentEmails.length);
    
    if (currentEmails.length === 0) {
        emailList.innerHTML = '<li>No emails found</li>';
        return;
    }
    
    // Clear the email list
    emailList.innerHTML = '';
    
    // Display first batch of emails
    showNextBatch();
    
    // Add scroll event listener for virtual scrolling
    emailList.addEventListener('scroll', handleScroll);
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
        
        return `
            <li class="email-item" data-id="${email.id}">
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
            const emailId = item.getAttribute('data-id');
            window.location.href = `email.html?id=${emailId}`;
        });
    });
    
    displayedCount = end;
}

function handleScroll() {
    // Check if we've scrolled near the bottom
    const { scrollTop, scrollHeight, clientHeight } = emailList;
    if (scrollHeight - scrollTop <= clientHeight + 100 && displayedCount < currentEmails.length) {
        showNextBatch();
    }
}

// Format date for display
function formatDate(dateString) {
    if (!dateString) return 'Unknown date';
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Perform full-text search using inverted index
function performSearch(term) {
    if (!term) return indexData;
    
    // Convert term to lowercase for case-insensitive search
    const lowerTerm = term.toLowerCase();
    
    // For simple implementation, we'll split the term into words and find emails containing any of those words
    const words = lowerTerm.split(/\s+/).filter(word => word.length > 0);
    
    if (words.length === 0) return indexData;
    
    // Find all email IDs that contain any of the search words
    const matchingIds = new Set();
    
    words.forEach(word => {
        // In a more sophisticated implementation, we might do fuzzy matching or stemming
        // For now, we'll look for exact matches
        if (searchIndex[word]) {
            // Convert integer IDs back to email filenames
            searchIndex[word].forEach(id => {
                const emailFilename = idMapping[id];
                if (emailFilename) {
                    matchingIds.add(emailFilename);
                }
            });
        }
    });
    
    // Filter main index data by matching IDs
    return indexData.filter(email => matchingIds.has(email.id));
}

// Filter emails by various criteria
function filterEmails() {
    const searchTerm = searchInput.value.trim();
    const fromTerm = fromFilter.value.toLowerCase();
    const toTerm = toFilter.value.toLowerCase();
    const startDate = dateStart.value;
    const endDate = dateEnd.value;
    
    // Start with either search results or all emails
    let filtered = searchTerm ? performSearch(searchTerm) : [...indexData];
    
    // Apply additional filters
    filtered = filtered.filter(email => {
        // From filter
        if (fromTerm && !email.from.toLowerCase().includes(fromTerm)) {
            return false;
        }
        
        // To filter
        if (toTerm && !email.to.toLowerCase().includes(toTerm)) {
            return false;
        }
        
        // Date range filter
        if (startDate && email.date < startDate) {
            return false;
        }
        
        if (endDate && email.date > endDate) {
            return false;
        }
        
        return true;
    });
    
    displayEmails(filtered);
}

// Initialize autocomplete for address fields
function initAutocomplete() {
    // Simple autocomplete implementation
    [fromFilter, toFilter].forEach(input => {
        input.addEventListener('input', () => {
            const value = input.value.toLowerCase();
            if (value.length > 2) {
                const matches = addresses.filter(addr => addr.includes(value));
                // In a real implementation, you would show these matches in a dropdown
                // For simplicity, we're just logging them
                console.log('Matches for', value, ':', matches);
            }
        });
    });
}

// Event listeners
searchButton.addEventListener('click', filterEmails);
searchInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') {
        filterEmails();
    }
});