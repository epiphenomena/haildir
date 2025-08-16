// Load email data
document.addEventListener('DOMContentLoaded', async () => {
    // Get email ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const emailId = urlParams.get('id');
    
    if (!emailId) {
        document.querySelector('.email-detail').innerHTML = '<p>Error: No email ID provided</p>';
        return;
    }
    
    try {
        // Load email data
        const emailResponse = await fetch(`emails/${emailId}.json`);
        if (!emailResponse.ok) {
            throw new Error(`Email not found: ${emailId}`);
        }
        
        const email = await emailResponse.json();
        
        // Update page with email data
        document.getElementById('email-subject').textContent = email.subject;
        document.getElementById('email-from').innerHTML = `<strong>From:</strong> ${escapeHtml(email.from)}`;
        document.getElementById('email-date').innerHTML = `<strong>Date:</strong> ${formatDate(email.date)}`;
        document.getElementById('email-to').innerHTML = `<strong>To:</strong> ${escapeHtml(email.to)}`;
        
        if (email.cc) {
            document.getElementById('email-cc').innerHTML = `<strong>Cc:</strong> ${escapeHtml(email.cc)}`;
            document.getElementById('email-cc').style.display = 'block';
        } else {
            document.getElementById('email-cc').style.display = 'none';
        }
        
        // Display email body
        const bodyElement = document.getElementById('email-body');
        if (email.body_html) {
            // If HTML body exists, display it in an iframe for safety
            const iframe = document.createElement('iframe');
            iframe.srcdoc = email.body_html;
            iframe.title = "Email content";
            bodyElement.innerHTML = '';
            bodyElement.appendChild(iframe);
        } else if (email.body_text) {
            // If only text body exists, display it as preformatted text
            bodyElement.innerHTML = `<pre>${escapeHtml(email.body_text)}</pre>`;
        } else {
            bodyElement.innerHTML = '<p>No content available</p>';
        }
        
        // Display attachments
        const attachmentsSection = document.getElementById('attachments-section');
        const attachmentList = document.getElementById('attachment-list');
        
        if (email.attachments && email.attachments.length > 0) {
            attachmentList.innerHTML = email.attachments.map(attachment => `
                <li class="attachment-item">
                    <a href="attachments/${attachment.saved_filename}" target="_blank">
                        <span class="attachment-icon">📎</span>
                        <span>${escapeHtml(attachment.filename)}</span>
                    </a>
                </li>
            `).join('');
            attachmentsSection.style.display = 'block';
        } else {
            attachmentsSection.style.display = 'none';
        }
        
    } catch (error) {
        console.error('Error loading email:', error);
        document.querySelector('.email-detail').innerHTML = `<p>Error loading email: ${error.message}</p>`;
    }
});

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