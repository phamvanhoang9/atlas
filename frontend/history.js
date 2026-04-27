/**
 * History Manager for ATLAS Research Platform
 * Handles persistent history storage, display, and interactions
 */

const HistoryUI = (() => {
    let currentHistoryId = null;
    let allHistoryData = [];

    const getAuthHeaders = () => {
        const token = window.localStorage.getItem("atlas_auth_token");
        return token ? { "Authorization": `Bearer ${token}` } : {};
    };

    const withAuthToken = (url) => {
        const token = window.localStorage.getItem("atlas_auth_token");
        if (!token) return url;
        const separator = url.includes("?") ? "&" : "?";
        return `${url}${separator}token=${encodeURIComponent(token)}`;
    };
    
    const init = () => {
        console.log("History UI initialized");
        
        // Toggle sidebar
        const toggleBtn = document.getElementById("historyToggle");
        const sidebar = document.getElementById("historySidebar");
        const closeBtn = document.getElementById("historyClose");
        
        if (toggleBtn) {
            toggleBtn.addEventListener("click", () => {
                sidebar.classList.toggle("open");
                toggleBtn.classList.toggle("active");
                if (sidebar.classList.contains("open")) {
                    loadHistory();
                }
            });
        }
        
        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                sidebar.classList.remove("open");
                toggleBtn.classList.remove("active");
            });
        }
        
        // Search functionality
        const searchInput = document.getElementById("historySearch");
        if (searchInput) {
            searchInput.addEventListener("input", (e) => {
                const searchTerm = e.target.value.toLowerCase();
                filterHistory(searchTerm);
            });
        }
        
        // Export history
        const exportBtn = document.getElementById("exportHistory");
        if (exportBtn) {
            exportBtn.addEventListener("click", exportHistory);
        }
        
        // Clear all history
        const clearBtn = document.getElementById("clearHistory");
        if (clearBtn) {
            clearBtn.addEventListener("click", clearAllHistory);
        }
        
        // Close sidebar when clicking outside
        document.addEventListener("click", (e) => {
            if (!sidebar.contains(e.target) && 
                !toggleBtn.contains(e.target) && 
                sidebar.classList.contains("open")) {
                sidebar.classList.remove("open");
                toggleBtn.classList.remove("active");
            }
        });
    };
    
    const loadHistory = async () => {
        const historyList = document.getElementById("historyList");
        historyList.innerHTML = `
            <div class="history-loading">
                <div class="history-loading-spinner"></div>
                <div>Đang tải lịch sử...</div>
            </div>
        `;
        
        try {
            const response = await fetch("/api/history", { headers: getAuthHeaders() });
            const data = await response.json();
            
            if (data.success) {
                allHistoryData = data.data;
                displayHistory(allHistoryData);
                updateStats(allHistoryData);
            } else {
                showError("Không thể tải lịch sử");
            }
        } catch (error) {
            console.error("Error loading history:", error);
            showError("Lỗi khi tải lịch sử");
        }
    };
    
    const displayHistory = (historyData) => {
        const historyList = document.getElementById("historyList");
        
        if (historyData.length === 0) {
            historyList.innerHTML = `
                <div class="history-empty">
                    <div class="history-empty-icon">📭</div>
                    <div>Chưa có lịch sử nghiên cứu</div>
                </div>
            `;
            return;
        }
        
        historyList.innerHTML = historyData.map(entry => createHistoryItemHTML(entry)).join("");
        
        // Add click handlers to items
        document.querySelectorAll(".history-item").forEach(item => {
            item.addEventListener("click", (e) => {
                // Don't trigger if clicking on action buttons
                if (e.target.closest(".history-item-action")) return;
                
                const entryId = item.dataset.id;
                loadHistoryEntry(entryId);
            });
        });
        
        // Add delete handlers
        document.querySelectorAll(".history-item-action.delete").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const entryId = btn.closest(".history-item").dataset.id;
                deleteHistoryEntry(entryId);
            });
        });
    };
    
    const createHistoryItemHTML = (entry) => {
        const date = new Date(entry.timestamp);
        const timeAgo = getTimeAgo(date);
        
        const modeClass = getModeClass(entry.mode);
        const modeLabel = getModeLabel(entry.mode);
        
        return `
            <div class="history-item" data-id="${entry.id}">
                <div class="history-item-header">
                    <span class="history-item-mode ${modeClass}">${modeLabel}</span>
                </div>
                <div class="history-item-query">${escapeHtml(entry.query)}</div>
                <div class="history-item-preview">${escapeHtml(entry.preview || 'Đang xử lý...')}</div>
                <div class="history-item-footer">
                    <span class="history-item-time">
                        🕐 ${timeAgo}
                    </span>
                    <div class="history-item-actions">
                        <button class="history-item-action delete" title="Xóa">
                            🗑️
                        </button>
                    </div>
                </div>
            </div>
        `;
    };
    
    const loadHistoryEntry = async (entryId) => {
        try {
            const response = await fetch(`/api/history/${entryId}`, { headers: getAuthHeaders() });
            const data = await response.json();
            
            if (data.success) {
                const entry = data.data;
                
                // Close sidebar
                document.getElementById("historySidebar").classList.remove("open");
                document.getElementById("historyToggle").classList.remove("active");
                
                // Scroll to top
                window.scrollTo(0, 0);
                
                // Fill in the form (but don't submit)
                document.querySelector('input[name="task"]').value = entry.query;
                document.querySelector('select[name="report_type"]').value = entry.mode;
                
                // Display the results
                displayStoredResults(entry);
                
                // Update mode description
                if (window.Atlas && window.Atlas.updateModeDescription) {
                    Atlas.updateModeDescription("modeDescription", "report_type");
                }
            }
        } catch (error) {
            console.error("Error loading history entry:", error);
            alert("Không thể tải lịch sử này");
        }
    };
    
    const displayStoredResults = (entry) => {
        // Hide initial sections
        document.getElementById("agentSection").style.display = "none";
        
        // Show results in READ section
        const readSection = document.getElementById("readSection");
        readSection.style.display = "block";
        
        // Convert markdown to HTML
        const converter = new showdown.Converter();
        const reportContainer = document.getElementById("reportContainer");
        reportContainer.innerHTML = converter.makeHtml(entry.report);
        
        // Update mode badge
        const modeBadge = document.getElementById("modeBadge");
        const badgeInfo = {
            'hỏi đáp': { text: '⚡ Hỏi đáp', class: 'qa' },
            'phân tích': { text: '📊 Phân tích', class: 'analysis' },
            'đề xuất bài báo': { text: '📚 Nghiên cứu', class: 'research' }
        };
        
        if (badgeInfo[entry.mode]) {
            modeBadge.textContent = badgeInfo[entry.mode].text;
            modeBadge.className = `mode-badge ${badgeInfo[entry.mode].class}`;
        }
        
        // Update download link
        if (entry.pdf_path) {
            document.getElementById("downloadLink").setAttribute("href", entry.pdf_path);
        }
        
        // Show THINK section if there are suggested questions
        if (entry.suggested_questions && entry.suggested_questions.length > 0) {
            if (window.Atlas && window.Atlas.storeSuggestedQuestions) {
                Atlas.storeSuggestedQuestions(entry.suggested_questions);
            }
            
            const thinkSection = document.getElementById("thinkSection");
            thinkSection.style.display = "block";
            
            // Populate suggested questions
            const questionsContainer = document.getElementById("suggestedQuestions");
            if (questionsContainer) {
                questionsContainer.innerHTML = entry.suggested_questions
                    .map(q => `<div class="suggested-question suggested-question-item">${escapeHtml(q)}</div>`)
                    .join("");
                
                // Add click handlers
                questionsContainer.querySelectorAll(".suggested-question-item").forEach(item => {
                    item.addEventListener("click", () => {
                        const taskInput = document.getElementById("task");
                        if (taskInput) {
                            taskInput.value = item.textContent;
                            taskInput.focus();
                            document.getElementById("form").scrollIntoView({ behavior: "smooth", block: "center" });
                        }
                    });
                });
            }
        }
        
        // Update status
        document.getElementById("status").textContent = "Đã tải từ lịch sử";
        document.getElementById("status").style.display = "block";
        
        // Enable report actions
        if (window.Atlas && window.Atlas.setReportActionsStatus) {
            Atlas.setReportActionsStatus("enabled");
        }
    };
    
    const deleteHistoryEntry = async (entryId) => {
        if (!confirm("Bạn có chắc muốn xóa lịch sử này?")) {
            return;
        }
        
        try {
            const response = await fetch(`/api/history/${entryId}`, {
                method: "DELETE",
                headers: getAuthHeaders()
            });
            const data = await response.json();
            
            if (data.success) {
                loadHistory(); // Reload the list
            } else {
                alert("Không thể xóa lịch sử");
            }
        } catch (error) {
            console.error("Error deleting history:", error);
            alert("Lỗi khi xóa lịch sử");
        }
    };
    
    const clearAllHistory = async () => {
        if (!confirm("Bạn có chắc muốn xóa TẤT CẢ lịch sử? Hành động này không thể hoàn tác!")) {
            return;
        }
        
        try {
            const response = await fetch("/api/history", {
                method: "DELETE",
                headers: getAuthHeaders()
            });
            const data = await response.json();
            
            if (data.success) {
                loadHistory(); // Reload the list (will show empty state)
            } else {
                alert("Không thể xóa lịch sử");
            }
        } catch (error) {
            console.error("Error clearing history:", error);
            alert("Lỗi khi xóa lịch sử");
        }
    };
    
    const exportHistory = async () => {
        try {
            window.open(withAuthToken("/api/history/export"), "_blank");
        } catch (error) {
            console.error("Error exporting history:", error);
            alert("Lỗi khi xuất lịch sử");
        }
    };
    
    const filterHistory = (searchTerm) => {
        if (!searchTerm) {
            displayHistory(allHistoryData);
            return;
        }
        
        const filtered = allHistoryData.filter(entry => 
            entry.query.toLowerCase().includes(searchTerm) ||
            (entry.preview && entry.preview.toLowerCase().includes(searchTerm))
        );
        
        displayHistory(filtered);
    };
    
    const updateStats = (historyData) => {
        const statsDiv = document.getElementById("historyStats");
        const totalSpan = document.getElementById("statTotal");
        
        if (historyData.length > 0) {
            statsDiv.style.display = "block";
            totalSpan.textContent = historyData.length;
        } else {
            statsDiv.style.display = "none";
        }
    };
    
    const showError = (message) => {
        const historyList = document.getElementById("historyList");
        historyList.innerHTML = `
            <div class="history-empty">
                <div class="history-empty-icon">⚠️</div>
                <div>${escapeHtml(message)}</div>
            </div>
        `;
    };
    
    const getModeClass = (mode) => {
        const modeMap = {
            'hỏi đáp': 'qa',
            'phân tích': 'analysis',
            'đề xuất bài báo': 'research'
        };
        return modeMap[mode] || 'qa';
    };
    
    const getModeLabel = (mode) => {
        const labelMap = {
            'hỏi đáp': '💬 Hỏi đáp',
            'phân tích': '📊 Phân tích',
            'đề xuất bài báo': '📚 Nghiên cứu'
        };
        return labelMap[mode] || mode;
    };
    
    const getTimeAgo = (date) => {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        
        if (diffMins < 1) return "Vừa xong";
        if (diffMins < 60) return `${diffMins} phút trước`;
        if (diffHours < 24) return `${diffHours} giờ trước`;
        if (diffDays < 7) return `${diffDays} ngày trước`;
        
        return date.toLocaleDateString("vi-VN");
    };
    
    const escapeHtml = (text) => {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    };
    
    const setCurrentHistoryId = (id) => {
        currentHistoryId = id;
    };
    
    const getCurrentHistoryId = () => {
        return currentHistoryId;
    };
    
    // Public API
    return {
        init,
        loadHistory,
        setCurrentHistoryId,
        getCurrentHistoryId,
        displayStoredResults
    };
})();

// Initialize when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", HistoryUI.init);
} else {
    HistoryUI.init();
}
