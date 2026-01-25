/**
 * TraceView Review Comment UI Module
 *
 * User interface for comment threads:
 * - Thread rendering (collapsible)
 * - Comment form (new thread, reply)
 * - Resolve/unresolve actions
 * - Position selection UI
 * - Click-to-highlight positions
 *
 * IMPLEMENTS REQUIREMENTS:
 *   REQ-tv-d00016: Review JavaScript Integration
 *   REQ-d00012: Click-to-Highlight Positions
 *   REQ-d00087: Position Resolution with Fallback
 */

// Ensure TraceView.review namespace exists
window.TraceView = window.TraceView || {};
TraceView.review = TraceView.review || {};

(function(review) {
    'use strict';

    // ==========================================================================
    // Templates
    // ==========================================================================

    /**
     * Create thread list container HTML
     * REQ-d00005: Support read-only mode for archived packages
     * @param {string} reqId - Requirement ID
     * @returns {string} HTML
     */
    function threadListTemplate(reqId) {
        const isArchiveMode = review.packages && review.packages.isArchiveMode;
        const addButtonHtml = isArchiveMode
            ? `<span class="rs-readonly-notice" title="Archived packages are read-only">Read Only</span>`
            : `<button class="rs-btn rs-btn-primary rs-add-comment-btn" title="Add comment">+ Add Comment</button>`;

        return `
            <div class="rs-thread-list${isArchiveMode ? ' rs-archive-mode' : ''}" data-req-id="${reqId}">
                <div class="rs-thread-list-header">
                    <h4>Comments</h4>
                    ${addButtonHtml}
                </div>
                <div class="rs-thread-list-content">
                    <div class="rs-threads"></div>
                    <div class="rs-no-threads" style="display: none;">
                        No comments yet.
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Create thread HTML
     * REQ-d00005-C: Hide action buttons in archive mode
     * @param {Thread} thread - Thread object
     * @returns {string} HTML
     */
    function threadTemplate(thread) {
        const resolvedClass = thread.resolved ? 'rs-thread-resolved' : '';
        const resolvedBadge = thread.resolved ?
            `<span class="rs-badge rs-badge-resolved">Resolved</span>` : '';
        const confidenceClass = getConfidenceClass(thread);
        const isArchiveMode = review.packages && review.packages.isArchiveMode;

        // REQ-d00005-C: No action buttons in archive mode
        const actionButtonsHtml = isArchiveMode ? '' : `
            ${thread.resolved ?
                `<button class="rs-btn rs-btn-sm rs-unresolve-btn">Reopen</button>` :
                `<button class="rs-btn rs-btn-sm rs-resolve-btn">Resolve</button>`
            }
        `;

        // REQ-d00005-C: No reply form in archive mode
        const replyHtml = isArchiveMode ? '' : `
            <div class="rs-reply-form" style="display: none;">
                <textarea class="rs-reply-input" placeholder="Write a reply..."></textarea>
                <div class="rs-reply-actions">
                    <button class="rs-btn rs-btn-primary rs-submit-reply">Reply</button>
                    <button class="rs-btn rs-cancel-reply">Cancel</button>
                </div>
            </div>
            <button class="rs-btn rs-btn-link rs-show-reply-btn">Reply</button>
        `;

        return `
            <div class="rs-thread ${resolvedClass}${isArchiveMode ? ' rs-archive-mode' : ''}" data-thread-id="${thread.threadId}">
                <div class="rs-thread-header">
                    <div class="rs-thread-meta">
                        <span class="rs-position-label ${confidenceClass}"
                              data-thread-id="${thread.threadId}"
                              data-position-type="${thread.position?.type || 'general'}"
                              title="Click to highlight in REQ... click again to clear">
                            ${getPositionIcon(thread)} ${getPositionLabel(thread)}
                        </span>
                        ${resolvedBadge}
                    </div>
                    <div class="rs-thread-actions">
                        ${actionButtonsHtml}
                        <button class="rs-btn rs-btn-sm rs-collapse-btn" title="Collapse">V</button>
                    </div>
                </div>
                <div class="rs-thread-body">
                    <div class="rs-comments">
                        ${thread.comments.map(c => commentTemplate(c)).join('')}
                    </div>
                    ${replyHtml}
                </div>
            </div>
        `;
    }

    /**
     * Create comment HTML
     * @param {Comment} comment - Comment object
     * @returns {string} HTML
     */
    function commentTemplate(comment) {
        return `
            <div class="rs-comment" data-comment-id="${comment.id}">
                <div class="rs-comment-header">
                    <span class="rs-author">${escapeHtml(comment.author)}</span>
                    <span class="rs-time">${formatTime(comment.timestamp)}</span>
                </div>
                <div class="rs-comment-body">
                    ${formatCommentBody(comment.body)}
                </div>
            </div>
        `;
    }

    /**
     * Create new comment form HTML
     * @param {string} reqId - Requirement ID
     * @returns {string} HTML
     */
    function newCommentFormTemplate(reqId) {
        return `
            <div class="rs-new-comment-form" data-req-id="${reqId}">
                <h4>New Comment</h4>
                <div class="rs-form-group">
                    <label>Position</label>
                    <select class="rs-position-type">
                        <option value="general">General (whole requirement)</option>
                        <option value="line">Specific line</option>
                        <option value="block">Line range</option>
                        <option value="word">Word/phrase</option>
                    </select>
                </div>
                <div class="rs-position-options" style="display: none;">
                    <div class="rs-line-options" style="display: none;">
                        <label>Line number</label>
                        <input type="number" class="rs-line-input" min="1" value="1">
                    </div>
                    <div class="rs-block-options" style="display: none;">
                        <label>Line range</label>
                        <input type="number" class="rs-block-start" min="1" value="1">
                        <span>to</span>
                        <input type="number" class="rs-block-end" min="1" value="1">
                    </div>
                    <div class="rs-word-options" style="display: none;">
                        <label>Word/phrase</label>
                        <input type="text" class="rs-keyword" placeholder="Enter word or phrase">
                        <label>Occurrence</label>
                        <input type="number" class="rs-keyword-occurrence" min="1" value="1">
                    </div>
                </div>
                <div class="rs-form-group">
                    <label>Comment</label>
                    <textarea class="rs-comment-body-input"
                              placeholder="Write your comment..." rows="4"></textarea>
                </div>
                <div class="rs-form-actions">
                    <button class="rs-btn rs-btn-primary rs-submit-comment">Add Comment</button>
                    <button class="rs-btn rs-cancel-comment">Cancel</button>
                </div>
            </div>
        `;
    }

    // ==========================================================================
    // Helper Functions
    // ==========================================================================

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatTime(isoString) {
        try {
            const date = new Date(isoString);
            const now = new Date();
            const diff = now - date;

            if (diff < 60000) return 'just now';
            if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
            if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
            if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';

            return date.toLocaleDateString();
        } catch (e) {
            return isoString;
        }
    }

    function formatCommentBody(body) {
        // Simple markdown-like formatting
        let html = escapeHtml(body);
        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // Italic
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        // Code
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');
        // Line breaks
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    /**
     * Get confidence class for position label styling
     * REQ-d00012: Click-to-Highlight Positions
     * REQ-d00087: Position Resolution with Fallback
     * @param {Thread} thread - Thread object
     * @returns {string} CSS class name
     */
    function getConfidenceClass(thread) {
        const resolvedPosition = thread.resolvedPosition;
        if (!resolvedPosition || thread.position?.type === 'general') {
            return 'rs-confidence-unanchored';
        }
        const confidence = resolvedPosition.confidence;
        if (confidence === 'EXACT') return 'rs-confidence-exact';
        if (confidence === 'APPROXIMATE') return 'rs-confidence-approximate';
        return 'rs-confidence-unanchored';
    }

    /**
     * Get highlight class for line highlighting based on confidence
     * REQ-d00012: Click-to-Highlight Positions
     * REQ-d00087: Position Resolution with Fallback
     * @param {Thread} thread - Thread object
     * @returns {string} CSS class name for highlighting
     */
    function getHighlightClassForThread(thread) {
        const resolvedPosition = thread.resolvedPosition;
        if (!resolvedPosition || thread.position?.type === 'general') {
            return 'rs-highlight-unanchored';
        }
        const confidence = resolvedPosition.confidence;
        if (confidence === 'EXACT') return 'rs-highlight-exact';
        if (confidence === 'APPROXIMATE') return 'rs-highlight-approximate';
        return 'rs-highlight-unanchored';
    }

    function getPositionIcon(thread) {
        switch (thread.position.type) {
            case review.PositionType.LINE: return '[L]';
            case review.PositionType.BLOCK: return '[B]';
            case review.PositionType.WORD: return '[W]';
            default: return '[G]';
        }
    }

    function getPositionTooltip(thread) {
        const pos = thread.position;
        switch (pos.type) {
            case review.PositionType.LINE:
                return `Line ${pos.lineNumber}`;
            case review.PositionType.BLOCK:
                return `Lines ${pos.lineRange[0]}-${pos.lineRange[1]}`;
            case review.PositionType.WORD:
                return `"${pos.keyword}" (occurrence ${pos.keywordOccurrence || 1})`;
            default:
                return 'General comment';
        }
    }

    function getPositionLabel(thread) {
        const pos = thread.position;
        switch (pos.type) {
            case review.PositionType.LINE:
                return `Line ${pos.lineNumber}`;
            case review.PositionType.BLOCK:
                return `Lines ${pos.lineRange[0]}-${pos.lineRange[1]}`;
            case review.PositionType.WORD:
                return `"${escapeHtml(pos.keyword)}"`;
            default:
                return 'General';
        }
    }

    // ==========================================================================
    // UI Components
    // ==========================================================================

    /**
     * Render thread list for a requirement
     * @param {Element} container - Container element
     * @param {string} reqId - Requirement ID
     */
    function renderThreadList(container, reqId) {
        container.innerHTML = threadListTemplate(reqId);

        const threads = review.state.getThreads(reqId);
        const threadsContainer = container.querySelector('.rs-threads');
        const noThreads = container.querySelector('.rs-no-threads');

        if (threads.length === 0) {
            noThreads.style.display = 'block';
        } else {
            threads.forEach(thread => {
                threadsContainer.insertAdjacentHTML('beforeend', threadTemplate(thread));
            });
            bindThreadEvents(container);
        }

        // Bind add comment button
        const addBtn = container.querySelector('.rs-add-comment-btn');
        if (addBtn) {
            addBtn.addEventListener('click', (event) => {
                // Stop propagation to prevent any parent handlers from clearing selection
                event.stopPropagation();
                showNewCommentForm(container, reqId);
            });
        }
    }
    review.renderThreadList = renderThreadList;

    /**
     * Show new comment form
     * REQ-d00005: Block in archive mode
     * @param {Element} container - Container element (optional - uses current selection if not provided)
     * @param {string} reqId - Requirement ID (optional - uses current selection if not provided)
     */
    function showNewCommentForm(container, reqId) {
        // REQ-d00005-C: Block comment creation in archive mode
        if (review.packages && review.packages.isArchiveMode) {
            alert('This package is archived and read-only.\n\nComments cannot be added to archived packages.');
            return;
        }

        // IMPORTANT: Capture line selection state FIRST, before any DOM manipulation
        // This prevents loss of selection due to focus changes or event handling
        const lineSelection = review.getLineSelection ? review.getLineSelection() : {
            type: window.selectedLineRange ? 'block' : (window.selectedLineNumber ? 'line' : null),
            lineNumber: window.selectedLineNumber,
            lineRange: window.selectedLineRange
        };
        // Make a copy of the values in case they get cleared
        const capturedSelection = {
            type: lineSelection.type,
            lineNumber: lineSelection.lineNumber,
            lineRange: lineSelection.lineRange ? { ...lineSelection.lineRange } : null
        };

        // If called without arguments, get from current review state
        if (!reqId) {
            reqId = review.selectedReqId;
            if (!reqId) {
                console.warn('showNewCommentForm: No REQ selected');
                return;
            }
        }
        if (!container) {
            // Find the comments section for the current REQ
            container = document.querySelector('.rs-comments-section[data-req-id="' + reqId + '"]') ||
                        document.querySelector('.rs-thread-list[data-req-id="' + reqId + '"]') ||
                        document.getElementById('rs-comments-content');
            if (!container) {
                console.warn('showNewCommentForm: No container found');
                return;
            }
        }

        // Check if form already exists
        let form = container.querySelector('.rs-new-comment-form');
        if (form) {
            form.remove();
        }

        container.insertAdjacentHTML('afterbegin', newCommentFormTemplate(reqId));
        form = container.querySelector('.rs-new-comment-form');

        // Position type change handler
        const posType = form.querySelector('.rs-position-type');
        const posOptions = form.querySelector('.rs-position-options');
        const lineOpts = form.querySelector('.rs-line-options');
        const blockOpts = form.querySelector('.rs-block-options');
        const wordOpts = form.querySelector('.rs-word-options');

        posType.addEventListener('change', () => {
            const val = posType.value;
            posOptions.style.display = val === 'general' ? 'none' : 'block';
            lineOpts.style.display = val === 'line' ? 'block' : 'none';
            blockOpts.style.display = val === 'block' ? 'block' : 'none';
            wordOpts.style.display = val === 'word' ? 'block' : 'none';
        });

        // Use the captured selection (captured at function start before any DOM changes)
        if (capturedSelection.lineRange && capturedSelection.lineRange.start && capturedSelection.lineRange.end) {
            // Range selection - lineRange is {start, end} object
            posType.value = 'block';
            posType.dispatchEvent(new Event('change'));
            const startInput = form.querySelector('.rs-block-start');
            const endInput = form.querySelector('.rs-block-end');
            if (startInput) startInput.value = capturedSelection.lineRange.start;
            if (endInput) endInput.value = capturedSelection.lineRange.end;
        } else if (capturedSelection.lineNumber) {
            // Single line selection
            posType.value = 'line';
            posType.dispatchEvent(new Event('change'));
            const lineInput = form.querySelector('.rs-line-input');
            if (lineInput) lineInput.value = capturedSelection.lineNumber;
        }

        // Submit handler
        form.querySelector('.rs-submit-comment').addEventListener('click', () => {
            submitNewComment(form, reqId);
        });

        // Cancel handler
        form.querySelector('.rs-cancel-comment').addEventListener('click', () => {
            form.remove();
        });

        // Focus textarea
        form.querySelector('.rs-comment-body-input').focus();
    }
    review.showNewCommentForm = showNewCommentForm;

    /**
     * Submit new comment
     * REQ-d00094: Threads must be owned by a package
     * @param {Element} form - Form element
     * @param {string} reqId - Requirement ID
     */
    function submitNewComment(form, reqId) {
        // REQ-d00001-B: Require explicit package selection
        const activePackageId = review.packages && review.packages.activeId;
        if (!activePackageId) {
            alert('Please select a package first.\n\nThreads must be owned by a package.');
            return;
        }

        // REQ-d00001-B: Verify the active package actually exists
        const activePackage = review.packages.items.find(p => p.packageId === activePackageId);
        if (!activePackage) {
            console.error('Active package not found in packages list:', activePackageId);
            alert('The selected package no longer exists.\n\nPlease select a different package.');
            // Clear the stale activePackageId
            review.packages.activeId = null;
            return;
        }

        const body = form.querySelector('.rs-comment-body-input').value.trim();
        if (!body) {
            alert('Please enter a comment');
            return;
        }

        const user = review.state.currentUser || 'anonymous';
        const posType = form.querySelector('.rs-position-type').value;

        // Get current REQ hash (would come from embedded data)
        const hash = window.REQ_CONTENT_DATA?.[reqId]?.hash || '00000000';

        // Create position based on type
        let position;
        switch (posType) {
            case 'line': {
                const lineNum = parseInt(form.querySelector('.rs-line-input').value, 10);
                position = review.CommentPosition.createLine(hash, lineNum);
                break;
            }
            case 'block': {
                const start = parseInt(form.querySelector('.rs-block-start').value, 10);
                const end = parseInt(form.querySelector('.rs-block-end').value, 10);
                position = review.CommentPosition.createBlock(hash, start, end);
                break;
            }
            case 'word': {
                const keyword = form.querySelector('.rs-keyword').value.trim();
                const occurrence = parseInt(form.querySelector('.rs-keyword-occurrence').value, 10);
                if (!keyword) {
                    alert('Please enter a word or phrase');
                    return;
                }
                position = review.CommentPosition.createWord(hash, keyword, occurrence);
                break;
            }
            default:
                position = review.CommentPosition.createGeneral(hash);
        }

        // REQ-d00094-A: Create thread with packageId
        const thread = review.Thread.create(reqId, user, position, body, activePackageId);
        review.state.addThread(thread);

        // Auto-change status to Review if currently Draft
        const reqData = window.REQ_CONTENT_DATA && window.REQ_CONTENT_DATA[reqId];
        if (reqData && reqData.status === 'Draft' && typeof review.toggleToReview === 'function') {
            review.toggleToReview(reqId).then(result => {
                if (result.success) {
                    console.log(`Auto-changed REQ-${reqId} status to Review`);
                }
            }).catch(err => {
                console.warn('Failed to auto-change status:', err);
            });
        }

        // Trigger change event
        document.dispatchEvent(new CustomEvent('traceview:thread-created', {
            detail: { thread, reqId }
        }));

        // Re-render the thread list
        // The form is inside #review-panel-content, find the thread list's parent container
        const threadList = form.closest('.rs-thread-list') ||
                          form.parentElement?.querySelector('.rs-thread-list');
        const reviewPanelContent = document.getElementById('review-panel-content');

        if (threadList && threadList.parentElement) {
            renderThreadList(threadList.parentElement, reqId);
        } else if (reviewPanelContent) {
            // Form is directly in review-panel-content, re-render there
            renderThreadList(reviewPanelContent, reqId);
        } else {
            form.remove();
        }
    }

    /**
     * Bind event handlers to thread elements
     * @param {Element} container - Container element
     */
    function bindThreadEvents(container) {
        // Collapse/expand buttons
        container.querySelectorAll('.rs-collapse-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const thread = btn.closest('.rs-thread');
                const body = thread.querySelector('.rs-thread-body');
                const isCollapsed = body.style.display === 'none';
                body.style.display = isCollapsed ? 'block' : 'none';
                btn.textContent = isCollapsed ? 'V' : '>';
            });
        });

        // Resolve buttons
        container.querySelectorAll('.rs-resolve-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const threadEl = btn.closest('.rs-thread');
                const threadId = threadEl.getAttribute('data-thread-id');
                resolveThread(threadId, container);
            });
        });

        // Unresolve buttons
        container.querySelectorAll('.rs-unresolve-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const threadEl = btn.closest('.rs-thread');
                const threadId = threadEl.getAttribute('data-thread-id');
                unresolveThread(threadId, container);
            });
        });

        // Reply buttons
        container.querySelectorAll('.rs-show-reply-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const thread = btn.closest('.rs-thread');
                const replyForm = thread.querySelector('.rs-reply-form');
                replyForm.style.display = 'block';
                btn.style.display = 'none';
                replyForm.querySelector('.rs-reply-input').focus();
            });
        });

        // Cancel reply
        container.querySelectorAll('.rs-cancel-reply').forEach(btn => {
            btn.addEventListener('click', () => {
                const thread = btn.closest('.rs-thread');
                const replyForm = thread.querySelector('.rs-reply-form');
                const showBtn = thread.querySelector('.rs-show-reply-btn');
                replyForm.style.display = 'none';
                replyForm.querySelector('.rs-reply-input').value = '';
                showBtn.style.display = 'inline-block';
            });
        });

        // Submit reply
        container.querySelectorAll('.rs-submit-reply').forEach(btn => {
            btn.addEventListener('click', () => {
                const threadEl = btn.closest('.rs-thread');
                submitReply(threadEl, container);
            });
        });

        // REQ-d00012: Position label click handler with toggle behavior
        container.querySelectorAll('.rs-position-label').forEach(positionLabel => {
            positionLabel.addEventListener('click', (e) => {
                e.stopPropagation();

                const threadId = positionLabel.getAttribute('data-thread-id');
                const isActive = positionLabel.classList.contains('rs-position-active');

                // Clear all other active position labels
                document.querySelectorAll('.rs-position-label.rs-position-active').forEach(el => {
                    el.classList.remove('rs-position-active');
                });

                if (isActive) {
                    // Toggle off - clear highlights
                    clearAllPositionHighlights();
                    const reqCard = document.querySelector(`[data-req-id]`);
                    if (reqCard) {
                        const lineContainer = reqCard.querySelector('.rs-lines-table');
                        clearCommentHighlights(lineContainer);
                    }
                } else {
                    // Toggle on - highlight and mark active
                    positionLabel.classList.add('rs-position-active');
                    highlightThreadPositionInCard(threadId, container);
                }
            });
        });

        // Hover to highlight position
        container.querySelectorAll('.rs-thread').forEach(threadEl => {
            threadEl.addEventListener('mouseenter', () => {
                const threadId = threadEl.getAttribute('data-thread-id');
                review.activateHighlight(threadId);
            });
            threadEl.addEventListener('mouseleave', () => {
                review.activateHighlight(null);
            });

            // Click to highlight position in REQ card
            threadEl.addEventListener('click', (e) => {
                // Don't trigger if clicking on buttons or reply form
                if (e.target.closest('button') || e.target.closest('.rs-reply-form') ||
                    e.target.closest('textarea') || e.target.closest('input')) {
                    return;
                }
                const threadId = threadEl.getAttribute('data-thread-id');
                highlightThreadPositionInCard(threadId, container);
            });
        });
    }

    /**
     * Highlight the position referenced by a thread in the REQ card
     * REQ-d00012: Click-to-Highlight Positions
     * @param {string} threadId - Thread ID
     * @param {Element} container - Container element
     */
    function highlightThreadPositionInCard(threadId, container) {
        // Get the reqId and find the thread
        const reqId = container.querySelector('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.closest('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.getAttribute('data-req-id') ||
                      (typeof currentReviewReqId !== 'undefined' ? currentReviewReqId : null);

        if (!reqId) return;

        const threads = review.state.getThreads(reqId);
        const thread = threads.find(t => t.threadId === threadId);
        if (!thread || !thread.position) return;

        const position = thread.position;

        // REQ-d00012: Get confidence-based highlight class
        const highlightClass = getHighlightClassForThread(thread);

        // Find the REQ card's line-numbered view
        const reqCard = document.getElementById(`req-card-${reqId}`);
        if (!reqCard) return;

        const lineContainer = reqCard.querySelector('.rs-lines-table');

        // Clear any existing highlights
        clearAllPositionHighlights();
        if (lineContainer) {
            clearCommentHighlights(lineContainer);
        }

        // REQ-d00012: For GENERAL position type, highlight the whole card
        if (position.type === 'general' || position.type === review.PositionType?.GENERAL) {
            reqCard.classList.add('rs-card-highlight');
            reqCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        if (!lineContainer) return;

        // Highlight based on position type
        let linesToHighlight = [];

        if (position.type === review.PositionType.LINE && position.lineNumber) {
            linesToHighlight = [position.lineNumber];
        } else if (position.type === review.PositionType.BLOCK && position.lineRange) {
            const [start, end] = position.lineRange;
            for (let i = start; i <= end; i++) {
                linesToHighlight.push(i);
            }
        } else if (position.type === review.PositionType.WORD && position.keyword) {
            // For word positions, try to find the line containing the keyword
            const reqData = window.REQ_CONTENT_DATA && window.REQ_CONTENT_DATA[reqId];
            if (reqData && reqData.body) {
                const foundLine = review.findKeywordOccurrence(
                    reqData.body,
                    position.keyword,
                    position.keywordOccurrence || 1
                );
                if (foundLine) {
                    linesToHighlight = [foundLine.line];
                }
            }
        }

        // Apply highlights and scroll to first highlighted line
        if (linesToHighlight.length > 0) {
            let firstRow = null;
            linesToHighlight.forEach(lineNum => {
                const lineRow = lineContainer.querySelector(`.rs-line-row[data-line="${lineNum}"]`);
                if (lineRow) {
                    lineRow.classList.add('rs-comment-highlight');
                    lineRow.classList.add(highlightClass);  // REQ-d00012: Add confidence class
                    lineRow.setAttribute('data-highlight-thread', threadId);  // REQ-d00012: Track thread
                    if (!firstRow) firstRow = lineRow;
                }
            });

            // Scroll the first highlighted line into view
            if (firstRow) {
                firstRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }
    review.highlightThreadPositionInCard = highlightThreadPositionInCard;

    /**
     * Clear all position highlights (card-level highlights for GENERAL position)
     * REQ-d00012: Click-to-Highlight Positions
     * REQ-d00087: Position Resolution with Fallback
     */
    function clearAllPositionHighlights() {
        // Clear card-level highlights (for GENERAL position)
        document.querySelectorAll('.rs-card-highlight').forEach(el => {
            el.classList.remove('rs-card-highlight');
        });
        // REQ-d00012: Clear highlight classes from req cards
        document.querySelectorAll('[data-req-id]').forEach(reqCard => {
            reqCard.classList.remove('rs-highlight-unanchored', 'rs-card-highlight');
        });
    }
    review.clearAllPositionHighlights = clearAllPositionHighlights;

    /**
     * Clear comment highlights from line container
     * REQ-d00012: Enhanced to remove all highlight-related classes and attributes
     * @param {Element} lineContainer - The lines table element
     */
    function clearCommentHighlights(lineContainer) {
        if (!lineContainer) return;
        // Remove all highlight-related classes and data attributes
        lineContainer.querySelectorAll('.rs-comment-highlight, .rs-highlight-exact, .rs-highlight-approximate, .rs-highlight-unanchored, .rs-highlight-active').forEach(el => {
            el.classList.remove('rs-comment-highlight', 'rs-highlight-exact', 'rs-highlight-approximate', 'rs-highlight-unanchored', 'rs-highlight-active');
            el.removeAttribute('data-highlight-thread');
        });
    }
    review.clearCommentHighlights = clearCommentHighlights;

    /**
     * Submit reply to a thread
     * @param {Element} threadEl - Thread element
     * @param {Element} container - Container element
     */
    function submitReply(threadEl, container) {
        const threadId = threadEl.getAttribute('data-thread-id');
        const replyInput = threadEl.querySelector('.rs-reply-input');
        const body = replyInput.value.trim();

        if (!body) {
            alert('Please enter a reply');
            return;
        }

        const user = review.state.currentUser || 'anonymous';
        // Look for data-req-id in the container or its children (thread-list element)
        const reqId = container.querySelector('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.closest('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.getAttribute('data-req-id');

        // Find thread in state
        if (reqId) {
            const threads = review.state.getThreads(reqId);
            const thread = threads.find(t => t.threadId === threadId);
            if (thread) {
                thread.addComment(user, body);

                // Trigger change event
                document.dispatchEvent(new CustomEvent('traceview:comment-added', {
                    detail: { thread, reqId, body }
                }));

                // Re-render - find the proper container
                const threadListEl = container.querySelector('.rs-thread-list') || container;
                const renderTarget = threadListEl.parentElement || container;
                renderThreadList(renderTarget, reqId);
            }
        }
    }

    /**
     * Resolve a thread
     * @param {string} threadId - Thread ID
     * @param {Element} container - Container element
     */
    function resolveThread(threadId, container) {
        const reqId = container.querySelector('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.closest('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.getAttribute('data-req-id');
        const user = review.state.currentUser || 'anonymous';

        if (reqId) {
            const threads = review.state.getThreads(reqId);
            const thread = threads.find(t => t.threadId === threadId);
            if (thread) {
                thread.resolve(user);

                // Trigger event
                document.dispatchEvent(new CustomEvent('traceview:thread-resolved', {
                    detail: { thread, reqId, user }
                }));

                // Re-render - find the proper container
                const threadListEl = container.querySelector('.rs-thread-list') || container;
                const renderTarget = threadListEl.parentElement || container;
                renderThreadList(renderTarget, reqId);
            }
        }
    }

    /**
     * Unresolve a thread
     * @param {string} threadId - Thread ID
     * @param {Element} container - Container element
     */
    function unresolveThread(threadId, container) {
        const reqId = container.querySelector('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.closest('[data-req-id]')?.getAttribute('data-req-id') ||
                      container.getAttribute('data-req-id');

        if (reqId) {
            const threads = review.state.getThreads(reqId);
            const thread = threads.find(t => t.threadId === threadId);
            if (thread) {
                thread.unresolve();

                // Trigger event
                document.dispatchEvent(new CustomEvent('traceview:thread-unresolved', {
                    detail: { thread, reqId }
                }));

                // Re-render - find the proper container
                const threadListEl = container.querySelector('.rs-thread-list') || container;
                const renderTarget = threadListEl.parentElement || container;
                renderThreadList(renderTarget, reqId);
            }
        }
    }

    /**
     * Get comment count for a requirement
     * @param {string} reqId - Requirement ID
     * @returns {Object} {total, unresolved}
     */
    function getCommentCount(reqId) {
        const threads = review.state.getThreads(reqId);
        return {
            total: threads.length,
            unresolved: threads.filter(t => !t.resolved).length
        };
    }
    review.getCommentCount = getCommentCount;

    // ==========================================================================
    // Review Panel Integration
    // ==========================================================================

    /**
     * Handle review panel ready event - add comments section
     * @param {CustomEvent} event - Event with reqId and sectionsContainer
     */
    function handleReviewPanelReady(event) {
        const { reqId, sectionsContainer } = event.detail;
        if (!sectionsContainer) return;

        // Create comments section
        const commentsSection = document.createElement('div');
        commentsSection.className = 'rs-comments-section';
        commentsSection.setAttribute('data-req-id', reqId);
        sectionsContainer.appendChild(commentsSection);

        // Render thread list
        renderThreadList(commentsSection, reqId);
    }

    // Register event listener
    document.addEventListener('traceview:review-panel-ready', handleReviewPanelReady);

    // ==========================================================================
    // RS Namespace Exports (REQ-d00012: Test Accessibility)
    // ==========================================================================
    // Export functions to RS namespace for test access
    if (typeof window.RS === 'undefined') {
        window.RS = {};
    }
    RS.highlightThreadPositionInCard = highlightThreadPositionInCard;
    RS.clearAllPositionHighlights = clearAllPositionHighlights;
    RS.clearCommentHighlights = clearCommentHighlights;

})(TraceView.review);
