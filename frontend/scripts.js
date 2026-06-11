const Atlas = (() => {
    let intelligentQuestions = null;  // Store intelligent questions from the server
    let currentSuggestedQuestions = [];  // Track current suggested questions
    const debugLog = () => {};
    
    const init = () => {
      debugLog("Atlas initialized");
      
      // Add form submit event listener
      const form = document.getElementById("researchForm");
      debugLog("Form element:", form);
      
      if (form) {
        form.addEventListener("submit", (e) => {
          debugLog("Form submitted, preventing default");
          e.preventDefault();
          e.stopPropagation();
          startResearch();
          return false;
        });
      } else {
        console.error("Form not found!");
      }
      
      const copyBtn = document.getElementById("copyToClipboard");
      if (copyBtn) {
        copyBtn.addEventListener("click", copyToClipboard);
      }
      
      // Add mode selector change handlers
      const modeSelector = document.getElementById("report_type");
      if (modeSelector) {
        modeSelector.addEventListener("change", () => updateModeDescription("modeDescription", "report_type"));
        updateModeDescription("modeDescription", "report_type");
      }
      
      updateState("initial");
    }

    const storeSuggestedQuestions = (questions) => {
      debugLog("Storing intelligent questions:", questions);
      intelligentQuestions = questions;
      currentSuggestedQuestions = questions;  // Store for history
      
      // Visual debug
      const container = document.getElementById("suggestedQuestions");
      if (container) {
        container.setAttribute('data-debug', `Received ${questions?.length || 0} questions`);
      }
            // Immediately update the UI if questions section is already visible
      const thinkSection = document.getElementById("thinkSection");
      if (thinkSection && thinkSection.style.display === "block") {
        debugLog("Think section is visible, updating questions now");
        generateSuggestedQuestions(false); // false = don't wait, render immediately
      } else {
        debugLog("Think section not visible yet, will update later. Display:", thinkSection?.style.display);
      }
      
      // Update history with suggested questions
      updateHistoryWithQuestions(questions);
    };
    
    const updateHistoryWithQuestions = async (questions) => {
      // Update the current history entry with suggested questions
      if (window.HistoryUI) {
        const historyId = HistoryUI.getCurrentHistoryId();
        if (historyId) {
          try {
            // Note: The server already stores suggested questions from websocket
            // This is just for logging/confirmation
            debugLog("Questions stored in history:", historyId);
          } catch (error) {
            console.error("Error updating history with questions:", error);
          }
        }
      }
    };
    
    const startResearch = () => {
      // Clear previous content
      intelligentQuestions = null;
      currentSuggestedQuestions = [];
      document.getElementById("output").innerHTML = "";
      document.getElementById("reportContainer").innerHTML = "";
      document.getElementById("suggestedQuestions").innerHTML = "";
      
      // Show agent section, hide others
      document.getElementById("agentSection").style.display = "block";
      document.getElementById("readSection").style.display = "none";
      document.getElementById("thinkSection").style.display = "none";
      setResearchFormBusy(true);
      
      // Get current mode
      const mode = document.querySelector('select[name="report_type"]').value;
      
      updateState("in_progress")
      
      // Mode-specific messages
      const messages = {
        'hỏi đáp': "⚡ Đang tìm câu trả lời nhanh...",
        'phân tích': "🔬 Đang phân tích sâu các nghiên cứu...",
        'đề xuất bài báo': "📚 Đang tìm kiếm các bài báo phù hợp..."
      };
  
      addAgentResponse({ output: messages[mode] || "🤔 Đang suy nghĩ về yêu cầu nghiên cứu..." });
  
      listenToSockEvents();
    };
  
    const listenToSockEvents = () => {
      const { protocol, host, pathname } = window.location;
      const authToken = window.localStorage.getItem("atlas_auth_token");
      const authQuery = authToken ? `?token=${encodeURIComponent(authToken)}` : "";
      const ws_uri = `${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}${pathname}ws${authQuery}`; // wss:// for encrypted connections, ws:// for unencripted connections
      const converter = new showdown.Converter(); // convert Markdown to HTML
      const socket = new WebSocket(ws_uri); // enables two-way communication between a client and a server
  
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        debugLog("Received message:", data.type, data);
        
        if (data.type === 'logs') {
          addAgentResponse(data);
        } else if (data.type === 'report') {
          writeReport(data, converter);
        } else if (data.type === 'suggested_questions') {
          debugLog("Received intelligent questions:", data.output);
          storeSuggestedQuestions(data.output);
        } else if (data.type === 'quality_check') {
          renderQualityCheck(data.output);
        } else if (data.type === 'history_id') {
          // Store history ID for this session
          if (window.HistoryUI) {
            HistoryUI.setCurrentHistoryId(data.output);
            debugLog("History ID stored:", data.output);
          }
        } else if (data.type === 'path') {
          updateState("finished")
          updateDownloadLink(data);

        }
      };
  
      socket.onopen = (event) => {
        const task = document.querySelector('input[name="task"]').value;
        const report_type = document.querySelector('select[name="report_type"]').value;
        const agent = document.querySelector('input[name="agent"]:checked').value;
  
        const requestData = {
          task: task,
          report_type: report_type,
          agent: agent,
        };
  
        socket.send(`start ${JSON.stringify(requestData)}`);
      };
    };
  
    const addAgentResponse = (data) => {
      const output = document.getElementById("output");
      const response = document.createElement("div");
      response.className = "agent_response";
      if (data.html === true) {
        response.innerHTML = data.output;
      } else {
        response.textContent = data.output ?? "";
      }
      output.appendChild(response);
      output.scrollTop = output.scrollHeight;
      output.style.display = "block";
      updateScroll();
    };

    const escapeHtml = (value) => {
      const div = document.createElement("div");
      div.textContent = String(value ?? "");
      return div.innerHTML;
    };

    const renderQualityCheck = (payload) => {
      if (!payload || typeof payload !== "object") {
        return;
      }

      const status = payload.passed ? "Đạt ngưỡng" : "Cần xem lại";
      const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
      const warningHtml = warnings.length
        ? `<ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
        : "<p>Không có cảnh báo.</p>";

      addAgentResponse({
        html: true,
        output: `
          <div class="quality-check">
            <strong>Kiểm tra chất lượng: ${escapeHtml(status)}</strong>
            <div>Điểm: ${escapeHtml(payload.score)} | URL trong báo cáo: ${escapeHtml(payload.report_url_count)} | URL hợp lệ: ${escapeHtml(payload.grounded_url_count)}/${escapeHtml(payload.context_url_count)}</div>
            ${warningHtml}
          </div>
        `
      });
    };
  
    const writeReport = (data, converter) => {
      const reportContainer = document.getElementById("reportContainer");
      const markdownOutput = converter.makeHtml(data.output);
      reportContainer.innerHTML = markdownOutput;
      updateScroll();
    };
  
    const updateDownloadLink = (data) => {
      const path = data.output;
      const downloadLink = document.getElementById("downloadLink");
      const downloadMeta = document.getElementById("downloadMeta");
      downloadLink.setAttribute("href", path);
      downloadLink.setAttribute("download", path.split("/").pop() || "atlas-report.pdf");
      if (downloadMeta) {
        downloadMeta.textContent = "PDF đã sẵn sàng để tải xuống.";
      }
    };
  
    const updateScroll = () => {
      window.scrollTo(0, document.body.scrollHeight);
    };
  
    const copyToClipboard = () => {
      const reportText = document.getElementById('reportContainer').innerText;
      const status = document.getElementById("status");
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(reportText).then(() => {
          if (status) status.textContent = "Đã sao chép báo cáo.";
        }).catch(() => fallbackCopyToClipboard(reportText, status));
        return;
      }
      fallbackCopyToClipboard(reportText, status);
    };

    const fallbackCopyToClipboard = (reportText, status) => {
      const textarea = document.createElement('textarea');
      textarea.id = 'temp_element';
      textarea.style.height = 0;
      textarea.value = reportText;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      if (status) status.textContent = "Đã sao chép báo cáo.";
    };

    const updateState = (state) => {
      var status = "";
      switch (state) {
        case "in_progress":
          status = "Đang nghiên cứu..."
          setResearchFormBusy(true);
          setReportActionsStatus("disabled");
          break;
        case "finished":
          status = "Nghiên cứu hoàn thành!"
          setResearchFormBusy(false, true);
          setReportActionsStatus("enabled");
          // Show READ and THINK while keeping the main form as the single input surface.
          showReadThinkAskFlow();
          break;
        case "error":
          status = "Nghiên cứu thất bại!"
          setResearchFormBusy(false);
          setReportActionsStatus("disabled");
          break;
        case "initial":
          status = ""
          setResearchFormBusy(false);
          setReportActionsStatus("hidden");
          break;
        default:
          setReportActionsStatus("disabled");
      }
      const statusElement = document.getElementById("status");
      statusElement.textContent = status;
      if (statusElement.textContent == "") {
        statusElement.style.display = "none";
      } else {
        statusElement.style.display = "block";
      }
    }
    
    const showReadThinkAskFlow = () => {
      // Get current mode
      const mode = document.querySelector('select[name="report_type"]').value;
      
      // Update mode badge
      const modeBadge = document.getElementById("modeBadge");
      const badgeInfo = {
        'hỏi đáp': { text: '⚡ Hỏi đáp', class: 'qa' },
        'phân tích': { text: '📊 Phân tích', class: 'analysis' },
        'đề xuất bài báo': { text: '📚 Nghiên cứu', class: 'research' }
      };
      
      if (badgeInfo[mode]) {
        modeBadge.textContent = badgeInfo[mode].text;
        modeBadge.className = `mode-badge ${badgeInfo[mode].class}`;
      }
      
      // Hide agent section
      document.getElementById("agentSection").style.display = "none";
      
      // Show READ section immediately
      document.getElementById("readSection").style.display = "block";
      updateScroll();
      
      // Mode-specific flows
      if (mode === 'hỏi đáp') {
        // Q&A mode: Fast flow - minimal THINK, quick to ASK NEXT
        setTimeout(() => {
          document.getElementById("thinkSection").style.display = "block";
          document.querySelector("#thinkSection .section-subtitle").textContent = "Câu hỏi liên quan để khám phá thêm";
          generateSuggestedQuestions(true); // true = wait for intelligent questions
          // Simplified takeaways for Q&A
          document.getElementById("keyTakeaways").innerHTML = `
            <li>Đọc lại câu trả lời để nắm rõ nội dung</li>
            <li>Click vào câu hỏi gợi ý bên cạnh</li>
            <li>Hoặc đặt câu hỏi mới của bạn</li>
          `;
          updateScroll();
        }, 300);
        
      } else if (mode === 'phân tích') {
        // Analysis mode: Detailed THINK section
        setTimeout(() => {
          document.getElementById("thinkSection").style.display = "block";
          document.querySelector("#thinkSection .section-subtitle").textContent = "Khám phá các khía cạnh liên quan và hướng nghiên cứu tiếp theo";
          generateSuggestedQuestions(true); // true = wait for intelligent questions
          document.getElementById("keyTakeaways").innerHTML = `
            <li>Xem xét các phương pháp được phân tích</li>
            <li>So sánh ưu nhược điểm của từng approach</li>
            <li>Nhận diện xu hướng và gaps nghiên cứu</li>
            <li>Đánh giá khả năng áp dụng thực tế</li>
          `;
          updateScroll();
        }, 500);
        
      } else {
        // Research mode: Full flow
        setTimeout(() => {
          document.getElementById("thinkSection").style.display = "block";
          document.querySelector("#thinkSection .section-subtitle").textContent = "Khám phá các khía cạnh liên quan và hướng nghiên cứu tiếp theo";
          generateSuggestedQuestions(true); // true = wait for intelligent questions
          document.getElementById("keyTakeaways").innerHTML = `
            <li>Xem xét các phương pháp được đề xuất</li>
            <li>So sánh với các nghiên cứu hiện có</li>
            <li>Tìm kiếm khoảng trống nghiên cứu</li>
            <li>Đọc papers có code để thực hành</li>
          `;
          updateScroll();
        }, 500);
        
      }
    }
    
    const generateSuggestedQuestions = (waitForIntelligent = false) => {
      debugLog("generateSuggestedQuestions called, waitForIntelligent:", waitForIntelligent, "intelligentQuestions:", intelligentQuestions);
      const container = document.getElementById("suggestedQuestions");
      
      // Debug info
      if (intelligentQuestions) {
        debugLog("Type:", typeof intelligentQuestions, "IsArray:", Array.isArray(intelligentQuestions), "Length:", intelligentQuestions?.length);
      }
      
      // Use intelligent questions from the server if available
      if (intelligentQuestions && Array.isArray(intelligentQuestions) && intelligentQuestions.length > 0) {
        debugLog("Using intelligent questions from server:", intelligentQuestions);
        container.innerHTML = '';
        intelligentQuestions.forEach((q, index) => {
          debugLog(`Question ${index + 1}:`, q);
          const div = document.createElement('div');
          div.className = 'suggested-question';
          div.textContent = q;
          div.onclick = () => {
            const taskInput = document.getElementById('task');
            taskInput.value = q;
            taskInput.focus();
            document.getElementById('form').scrollIntoView({ behavior: 'smooth', block: 'center' });
          };
          container.appendChild(div);
        });
        debugLog("Rendered", intelligentQuestions.length, "intelligent questions");
        return;
      }
      
      // If we should wait for intelligent questions, show loading state
      if (waitForIntelligent) {
        debugLog("Waiting for intelligent questions from server...");
        const debugInfo = intelligentQuestions ? ` (Already have: ${intelligentQuestions.length})` : '';
        container.innerHTML = '';
        const loadingQuestion = document.createElement('div');
        loadingQuestion.className = 'suggested-question suggested-question-loading';
        loadingQuestion.textContent = `💭 Đang tạo câu hỏi thông minh dựa trên kết quả nghiên cứu...${debugInfo}`;
        container.appendChild(loadingQuestion);
        
        // Wait up to 8 seconds for intelligent questions from the server
        const maxWaitTime = 8000;
        const startTime = Date.now();
        let checkCount = 0;
        
        const checkInterval = setInterval(() => {
          checkCount++;
          debugLog(`Check #${checkCount}: intelligentQuestions =`, intelligentQuestions);
          
          if (intelligentQuestions && Array.isArray(intelligentQuestions) && intelligentQuestions.length > 0) {
            debugLog("Intelligent questions received! Rendering...");
            clearInterval(checkInterval);
            generateSuggestedQuestions(false); // Render the questions
          } else if (Date.now() - startTime > maxWaitTime) {
            debugLog("Timeout waiting for intelligent questions, using fallback");
            clearInterval(checkInterval);
            // Timeout: fall back to template questions
            intelligentQuestions = null;
            generateSuggestedQuestions(false);
          }
        }, 200);
        
        return;
      }
      
      // Fallback: template-based questions
      debugLog("Using fallback template-based questions");
      container.innerHTML = '';
      const taskInput = document.querySelector('input[name="task"]').value;
      const mode = document.querySelector('select[name="report_type"]').value;
      
      let questions = [];
      if (mode === 'hỏi đáp') {
        questions = [
          `${taskInput} hoạt động như thế nào?`,
          `Ưu nhược điểm của ${taskInput}?`,
          `Ví dụ thực tế về ${taskInput}?`,
          `So sánh ${taskInput} với các phương pháp khác?`
        ];
      } else if (mode === 'phân tích') {
        questions = [
          `So sánh chi tiết các phương pháp trong ${taskInput}`,
          `Xu hướng mới nhất về ${taskInput}?`,
          `Thách thức chính trong ${taskInput}?`,
          `State-of-the-art methods cho ${taskInput}?`
        ];
      } else {
        questions = [
          `Tìm papers về ${taskInput} có code implementation`,
          `Survey papers về ${taskInput}?`,
          `Benchmark datasets cho ${taskInput}?`,
          `Tutorial và resources học ${taskInput}?`
        ];
      }
      
      questions.forEach(q => {
        const div = document.createElement('div');
        div.className = 'suggested-question';
        div.textContent = q;
        div.onclick = () => {
          const taskInput = document.getElementById('task');
          taskInput.value = q;
          taskInput.focus();
          document.getElementById('form').scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
        container.appendChild(div);
      });
    }
    
    const updateModeDescription = (descriptionId, selectorId) => {
      const mode = document.getElementById(selectorId).value;
      const description = document.getElementById(descriptionId);
      
      const descriptions = {
        'hỏi đáp': '💬 Nhận câu trả lời nhanh, ngắn gọn và chính xác cho câu hỏi của bạn',
        'phân tích': '📊 Phân tích sâu, so sánh các phương pháp, và đánh giá xu hướng nghiên cứu',
        'đề xuất bài báo': '📚 Danh sách bài báo được xếp hạng theo độ liên quan và chất lượng'
      };
      
      if (description) {
        description.textContent = descriptions[mode] || '';
      }
    }

    /**
     * Shows or hides the download and copy buttons.
     */
    const setReportActionsStatus = (status) => {
      const reportActions = document.getElementById("reportActions");
      if (!reportActions) {
        return;
      }

      if (status == "enabled") {
        reportActions.querySelectorAll("a, button").forEach((link) => {
          link.classList.remove("disabled");
          link.removeAttribute("disabled");
          link.removeAttribute('onclick');
          reportActions.style.display = "block";
        });
      } else {
        reportActions.querySelectorAll("a, button").forEach((link) => {
          link.classList.add("disabled");
          if (link.tagName === "BUTTON") {
            link.setAttribute("disabled", "disabled");
          } else {
            link.setAttribute('onclick', "return false;");
          }
        });
        if (status == "hidden") {
          reportActions.style.display = "none";
        }
      }
    }

    const setResearchFormBusy = (busy, completed = false) => {
      const submitButton = document.getElementById("submitResearch");
      const taskLabel = document.querySelector("label[for='task']");
      const form = document.getElementById("researchForm");
      if (!submitButton || !taskLabel || !form) {
        return;
      }

      submitButton.disabled = busy;
      form.classList.toggle("research-form-complete", completed && !busy);
      if (busy) {
        submitButton.value = "Đang nghiên cứu...";
        taskLabel.textContent = "ATLAS đang xử lý yêu cầu";
      } else if (completed) {
        submitButton.value = "Nghiên cứu tiếp";
        taskLabel.textContent = "Bạn muốn khám phá gì tiếp theo?";
      } else {
        submitButton.value = "Nghiên cứu";
        taskLabel.textContent = "Bạn muốn khám phá gì?";
      }
    }

    document.addEventListener("DOMContentLoaded", init);
    return {
      startResearch,
      copyToClipboard,
      setReportActionsStatus,
      storeSuggestedQuestions,
      updateModeDescription,
    };
  })();

window.Atlas = Atlas;
