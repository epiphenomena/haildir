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
const hasAttachment = document.getElementById('has-attachment');

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
    const hasAttachmentFilter = hasAttachment.checked;
    
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
        
        // Attachment filter
        if (hasAttachmentFilter && !email.has_attachments) {
            return false;
        }
        
        return true;
    });
    
    displayEmails(filtered);
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

// Event listeners
searchButton.addEventListener('click', filterEmails);
searchInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') {
        filterEmails();
    }
});