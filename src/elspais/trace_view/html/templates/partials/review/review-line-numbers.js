/**
 * TraceView Review Line Numbers Module
 * Add line numbers to requirement content for click-to-comment.
 * IMPLEMENTS REQUIREMENTS: REQ-d00012
 */
window.TraceView = window.TraceView || {};
TraceView.review = TraceView.review || {};
window.ReviewSystem = window.ReviewSystem || {};
var RS = window.ReviewSystem;

// Global selection state (REQ-d00012-H)
window.selectedLineNumber = null;
window.selectedLineRange = null;

(function(review, RS) {
    'use strict';

    // Track current selection state
    let currentReqId = null;
    let selectionType = 'general';  // 'line', 'block', or 'general'

    // Drag selection state
    let isDragging = false;
    let dragStartLine = null;
    let dragContainer = null;
    let dragReqId = null;

    /**
     * Convert markdown content to line-numbered HTML view
     * @param {string} content - Raw markdown/text content
     * @param {string} reqId - The requirement ID
     * @returns {HTMLElement} Container element with line-numbered content
     */
    function convertToLineNumberedView(content, reqId) {
        const container = document.createElement('div');
        container.className = 'rs-line-numbers-container';
        container.setAttribute('data-req-id', reqId);

        // Create hint bar (shows click instructions in review mode)
        const hint = document.createElement('div');
        hint.className = 'rs-line-numbers-hint';
        hint.textContent = 'Click or drag to select lines for commenting';
        container.appendChild(hint);

        // Create table structure for line numbers
        const table = document.createElement('div');
        table.className = 'rs-lines-table';

        const lines = (content || '').split('\n');
        lines.forEach((line, index) => {
            const row = document.createElement('div');
            row.className = 'rs-line-row';
            row.setAttribute('data-line', index + 1);
            row.style.cursor = 'pointer';

            // Mousedown handler to start selection/drag
            row.addEventListener('mousedown', function(event) {
                event.preventDefault(); // Prevent text selection
                handleLineMouseDown(event, reqId, index + 1, container);
            });

            // Mouseover handler for drag selection
            row.addEventListener('mouseover', function(event) {
                if (isDragging && dragContainer === container) {
                    handleLineDragOver(reqId, index + 1, container);
                }
            });

            // Line number
            const lineNum = document.createElement('span');
            lineNum.className = 'rs-line-number';
            lineNum.textContent = index + 1;

            // Line text
            const lineText = document.createElement('span');
            lineText.className = 'rs-line-text';
            lineText.textContent = line || ' ';  // Preserve empty lines

            row.appendChild(lineNum);
            row.appendChild(lineText);
            table.appendChild(row);
        });

        container.appendChild(table);
        return container;
    }

    /**
     * Handle mousedown on a line - start selection or drag
     * @param {MouseEvent} event - Mouse event
     * @param {string} reqId - Requirement ID
     * @param {number} lineNumber - Line number
     * @param {HTMLElement} container - Container element
     */
    function handleLineMouseDown(event, reqId, lineNumber, container) {
        // Start drag tracking
        isDragging = true;
        dragStartLine = lineNumber;
        dragContainer = container;
        dragReqId = reqId;

        // Select the starting line
        selectSingleLine(reqId, lineNumber, container);

        // Dispatch initial selection event
        dispatchSelectionEvent(reqId, lineNumber);
    }

    /**
     * Handle mouseover during drag - extend selection
     * @param {string} reqId - Requirement ID
     * @param {number} lineNumber - Line number being hovered
     * @param {HTMLElement} container - Container element
     */
    function handleLineDragOver(reqId, lineNumber, container) {
        if (!isDragging || dragStartLine === null) return;

        if (lineNumber !== dragStartLine) {
            // Extend selection to range
            selectLineRange(reqId, dragStartLine, lineNumber, container);
        } else {
            // Back to single line
            selectSingleLine(reqId, lineNumber, container);
        }
    }

    /**
     * Handle mouseup - finalize selection
     */
    function handleLineMouseUp() {
        if (isDragging && dragReqId) {
            // Dispatch final selection event
            dispatchSelectionEvent(dragReqId, window.selectedLineNumber);
        }

        // Reset drag state
        isDragging = false;
        dragStartLine = null;
        dragContainer = null;
        dragReqId = null;
    }

    /**
     * Dispatch selection event for line selection
     * @param {string} reqId - Requirement ID
     * @param {number} lineNumber - Primary line number
     */
    function dispatchSelectionEvent(reqId, lineNumber) {
        // Dispatch event for line selection (REQ-d00012-C)
        document.dispatchEvent(new CustomEvent('rs:line-selected', {
            detail: {
                reqId: reqId,
                lineNumber: lineNumber,
                lineRange: window.selectedLineRange,
                selectionType: selectionType
            }
        }));

        // Also update Review Panel focus to this REQ
        const req = window.REQ_CONTENT_DATA ? window.REQ_CONTENT_DATA[reqId] : null;
        document.dispatchEvent(new CustomEvent('traceview:req-selected', {
            detail: { reqId: reqId, req: req }
        }));
    }

    /**
     * Handle click on a line (legacy support, also handles shift-click)
     * @param {Event} event - Click event
     * @param {string} reqId - Requirement ID
     * @param {number} lineNumber - Line number clicked
     * @param {HTMLElement} container - Container element
     */
    function handleLineClick(event, reqId, lineNumber, container) {
        if (event.shiftKey && window.selectedLineNumber !== null) {
            // Shift-click: select range
            selectLineRange(reqId, window.selectedLineNumber, lineNumber, container);
        } else {
            // Single click: select single line
            selectSingleLine(reqId, lineNumber, container);
        }

        dispatchSelectionEvent(reqId, lineNumber);
    }

    // Global mouseup handler to finalize drag selection
    document.addEventListener('mouseup', handleLineMouseUp);

    /**
     * Select a single line
     * @param {string} reqId - Requirement ID
     * @param {number} lineNumber - Line number to select
     * @param {HTMLElement} container - Container element (optional)
     */
    function selectSingleLine(reqId, lineNumber, container) {
        currentReqId = reqId;
        window.selectedLineNumber = lineNumber;
        window.selectedLineRange = null;
        selectionType = 'line';

        // Clear previous selection
        if (container) {
            const prev = container.querySelectorAll('.rs-line-row.selected');
            prev.forEach(el => el.classList.remove('selected'));

            // Highlight selected line
            const row = container.querySelector(`.rs-line-row[data-line="${lineNumber}"]`);
            if (row) {
                row.classList.add('selected');
            }
        }
    }

    /**
     * Select a range of lines
     * @param {string} reqId - Requirement ID
     * @param {number} startLine - Start line number
     * @param {number} endLine - End line number
     * @param {HTMLElement} container - Container element (optional)
     */
    function selectLineRange(reqId, startLine, endLine, container) {
        currentReqId = reqId;
        const start = Math.min(startLine, endLine);
        const end = Math.max(startLine, endLine);
        window.selectedLineNumber = start;
        window.selectedLineRange = { start: start, end: end };
        selectionType = 'block';

        // Clear previous selection
        if (container) {
            const prev = container.querySelectorAll('.rs-line-row.selected');
            prev.forEach(el => el.classList.remove('selected'));

            // Highlight range
            for (let i = start; i <= end; i++) {
                const row = container.querySelector(`.rs-line-row[data-line="${i}"]`);
                if (row) {
                    row.classList.add('selected');
                }
            }
        }
    }

    /**
     * Apply line numbers to a requirement card
     * @param {HTMLElement} cardElement - The card element containing the requirement
     * @param {string} reqId - The requirement ID
     */
    function applyLineNumbersToCard(cardElement, reqId) {
        if (!cardElement) return;

        // Find the body section of the requirement card
        const bodySection = cardElement.querySelector('.req-body-section');
        if (!bodySection) return;

        // Check if already fully processed (has our container with click handlers)
        if (bodySection.querySelector('.rs-line-numbers-container')) {
            return;
        }

        // Check if line numbers already exist (from scripts.js renderMarkdownWithLines)
        // If so, just add click handlers instead of recreating
        const existingTable = bodySection.querySelector('.rs-lines-table');
        if (existingTable) {
            // Add wrapper container with hint
            const container = document.createElement('div');
            container.className = 'rs-line-numbers-container';
            container.setAttribute('data-req-id', reqId);

            // Create hint bar
            const hint = document.createElement('div');
            hint.className = 'rs-line-numbers-hint';
            hint.textContent = 'Click or drag to select lines for commenting';
            container.appendChild(hint);

            // Move existing table into container
            existingTable.parentNode.insertBefore(container, existingTable);
            container.appendChild(existingTable);

            // Add drag selection handlers to entire rows
            const rows = existingTable.querySelectorAll('.rs-line-row');
            rows.forEach(row => {
                const lineNumber = parseInt(row.getAttribute('data-line'), 10);
                if (lineNumber) {
                    // Mousedown to start selection/drag
                    row.addEventListener('mousedown', function(event) {
                        event.preventDefault(); // Prevent text selection
                        handleLineMouseDown(event, reqId, lineNumber, container);
                    });

                    // Mouseover for drag selection
                    row.addEventListener('mouseover', function(event) {
                        if (isDragging && dragContainer === container) {
                            handleLineDragOver(reqId, lineNumber, container);
                        }
                    });

                    row.style.cursor = 'pointer';
                }
            });

            bodySection.classList.add('rs-with-line-numbers');
            return;
        }

        // No existing line numbers - create from scratch
        const content = bodySection.textContent || '';
        const container = convertToLineNumberedView(content, reqId);

        // Replace content with line-numbered version
        bodySection.innerHTML = '';
        bodySection.appendChild(container);
        bodySection.classList.add('rs-with-line-numbers');
    }

    /**
     * Get current line selection state
     * @returns {Object} Selection state with type, lineNumber, and lineRange
     */
    function getLineSelection() {
        return {
            type: selectionType,
            lineNumber: window.selectedLineNumber,
            lineRange: window.selectedLineRange,
            reqId: currentReqId
        };
    }

    /**
     * Clear line selection for a specific card
     * @param {HTMLElement} cardElement - The card element
     */
    function clearLineSelection(cardElement) {
        if (!cardElement) return;

        const highlights = cardElement.querySelectorAll('.rs-line-row.selected');
        highlights.forEach(el => el.classList.remove('selected'));

        // Reset global state if this was the active selection
        const container = cardElement.querySelector('.rs-line-numbers-container');
        if (container && container.getAttribute('data-req-id') === currentReqId) {
            window.selectedLineNumber = null;
            window.selectedLineRange = null;
            selectionType = 'general';
            currentReqId = null;
        }
    }

    /**
     * Clear all line selections across all cards
     */
    function clearAllLineSelections() {
        const containers = document.querySelectorAll('.rs-line-numbers-container');
        containers.forEach(container => {
            const highlights = container.querySelectorAll('.rs-line-row.selected');
            highlights.forEach(el => el.classList.remove('selected'));
        });

        // Reset global state
        window.selectedLineNumber = null;
        window.selectedLineRange = null;
        selectionType = 'general';
        currentReqId = null;
    }

    /**
     * Highlight a specific line in a requirement card
     * @param {HTMLElement} cardElement - The card element
     * @param {number} lineNumber - The line number to highlight
     */
    function highlightLine(cardElement, lineNumber) {
        if (!cardElement) return;

        // Remove existing highlights
        const existingHighlights = cardElement.querySelectorAll('.rs-line-row.selected');
        existingHighlights.forEach(el => el.classList.remove('selected'));

        // Add highlight to target line
        const targetRow = cardElement.querySelector(`.rs-line-row[data-line="${lineNumber}"]`);
        if (targetRow) {
            targetRow.classList.add('selected');
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    /**
     * Clear all line highlights in a card (alias for clearLineSelection)
     * @param {HTMLElement} cardElement - The card element
     */
    function clearLineHighlights(cardElement) {
        clearLineSelection(cardElement);
    }

    /**
     * Handle keyboard events for line selection (REQ-d00012-I)
     * @param {KeyboardEvent} event - Keyboard event
     */
    function handleKeyboard(event) {
        if (event.key === 'Escape') {
            clearAllLineSelections();
            document.dispatchEvent(new CustomEvent('rs:line-selection-cleared'));
        }
    }

    // Bind keyboard handler (REQ-d00012-I)
    document.addEventListener('keydown', handleKeyboard);

    // Export to review namespace
    review.convertToLineNumberedView = convertToLineNumberedView;
    review.applyLineNumbersToCard = applyLineNumbersToCard;
    review.getLineSelection = getLineSelection;
    review.clearLineSelection = clearLineSelection;
    review.clearAllLineSelections = clearAllLineSelections;
    review.highlightLine = highlightLine;
    review.clearLineHighlights = clearLineHighlights;
    review.selectSingleLine = selectSingleLine;
    review.selectLineRange = selectLineRange;
    review.handleLineClick = handleLineClick;
    review.handleKeyboard = handleKeyboard;

    // Export to ReviewSystem alias (RS) pattern for tests
    RS.convertToLineNumberedView = convertToLineNumberedView;
    RS.applyLineNumbersToCard = applyLineNumbersToCard;
    RS.getLineSelection = getLineSelection;
    RS.clearLineSelection = clearLineSelection;
    RS.clearAllLineSelections = clearAllLineSelections;
    RS.highlightLine = highlightLine;
    RS.clearLineHighlights = clearLineHighlights;

})(TraceView.review, RS);
