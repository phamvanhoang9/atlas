# History Feature Documentation

## Overview
The ATLAS research platform includes a comprehensive history feature that persistently stores all research queries and results. Users can revisit previous searches, continue conversations, and never lose their research progress.

## Features Implemented

### 1. **Persistent Storage**
- **Server-side JSON storage** in `history.json` file
- Automatic saving of all research queries and results
- Thread-safe operations for concurrent access
- Data persists across sessions and browser refreshes

### 2. **History Sidebar UI**
- **Elegant slide-in sidebar** accessible from top-right button (📚)
- Beautiful gradient styling matching ATLAS brand
- Real-time search functionality
- Statistics display showing total entries
- Smooth animations and transitions

### 3. **History Entry Information**
Each history entry stores:
- Unique ID
- Timestamp
- User query
- Research mode (Hỏi đáp, Phân tích, Đề xuất bài báo)
- Full markdown report
- Generated PDF path
- Intelligent suggested questions
- Preview snippet (first 200 characters)

### 4. **User Interactions**

#### Viewing History
- Click the **📚 button** in top-right corner to open history sidebar
- Entries are displayed newest first
- Each entry shows:
  - Mode badge (color-coded by type)
  - Query text
  - Preview of results
  - Time ago (e.g., "5 phút trước", "2 giờ trước")

#### Loading Previous Research
- **Click any history entry** to instantly load it
- Displays full report in READ section
- Populates suggested questions in THINK section
- Updates form fields with query and mode
- Ready to continue with follow-up questions

#### Search History
- Type in search box to filter entries in real-time
- Searches both query text and report content
- Instant results as you type

#### Delete Entries
- Click **🗑️ button** on any entry to delete it
- Confirmation dialog prevents accidental deletion
- Entry removed immediately from list

#### Export History
- Click **📥 Xuất** button to download all history
- Exports to JSON file with complete data
- Useful for backup or data analysis

#### Clear All History
- Click **🗑️ Xóa tất** button to clear entire history
- Double confirmation prevents accidental loss
- Irreversible action

### 5. **Backend API Endpoints**

```
GET    /api/history              - Get all history entries
GET    /api/history/{id}         - Get specific entry
DELETE /api/history/{id}         - Delete specific entry
DELETE /api/history              - Clear all history
GET    /api/history/search/{term} - Search entries
GET    /api/history/export       - Export to JSON
GET    /api/history/stats        - Get statistics
```

## Architecture

### Backend Components

#### `src/storage/history.py`
- **HistoryManager class**: Core history management
- Thread-safe operations with Lock
- JSON file storage and retrieval
- Search and filtering capabilities
- Statistics generation
- Export functionality

#### `src/api/app.py`
- RESTful API endpoints for history
- WebSocket integration for real-time updates
- Automatic history creation on research start
- Updates history with results and PDF path
- Captures suggested questions from agent

#### `src/utils/websocket_manager.py`
- Enhanced to track suggested questions
- WebsocketWrapper class captures outgoing messages
- Stores questions per connection
- Passes questions to server for history update

### Frontend Components

#### `frontend/history.js`
- **HistoryUI module**: Complete history UI logic
- Sidebar toggle and navigation
- Real-time search filtering
- Entry loading and display
- Delete and export operations
- Beautiful HTML generation for entries

#### `frontend/scripts.js`
- Integration with existing research flow
- Receives and stores history ID
- Tracks suggested questions
- Exports utility functions for history UI

#### `frontend/index.html`
- History sidebar structure
- Toggle button
- Search input
- Action buttons

#### `frontend/styles.css`
- Complete styling for history feature
- Gradient backgrounds and smooth transitions
- Responsive design
- Color-coded mode badges
- Hover effects and animations

## Data Flow

### Research Session Flow
1. User submits research query
2. Backend creates history entry, returns ID
3. Frontend stores history ID
4. Agent processes query, streams results
5. Suggested questions sent via WebSocket
6. WebSocket wrapper captures questions
7. Backend updates history with:
   - Complete report
   - PDF path
   - Suggested questions
8. History entry now complete

### Loading History Flow
1. User clicks history entry
2. Frontend fetches full entry via API
3. Displays report in READ section
4. Populates suggested questions
5. Updates form fields
6. Shows THINK and ASK NEXT sections
7. User can continue research

## Storage Schema

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-14T10:30:45.123456",
  "query": "Agentic AI",
  "mode": "phân tích",
  "report": "# Full markdown report...",
  "suggested_questions": [
    "Question 1?",
    "Question 2?",
    "Question 3?"
  ],
  "pdf_path": "/outputs/report_123.pdf",
  "preview": "First 200 characters of report..."
}
```

## Usage Examples

### Example 1: Continuing Previous Research
```javascript
// User clicks history entry with ID "abc-123"
// Frontend loads entry and displays it
// User can now ask follow-up questions in context
```

### Example 2: Searching History
```javascript
// User types "deep learning" in search box
// History filters to show only matching entries
// Instant results without page reload
```

### Example 3: Exporting History
```javascript
// User clicks Export button
// Browser downloads history_export.json
// Contains all research history in structured format
```

## Technical Considerations

### Storage Choice: Server-Side
**Why server-side instead of client-side?**
- ✅ Cross-device synchronization potential
- ✅ No browser storage limits (localStorage ~5-10MB)
- ✅ Easier backup and migration
- ✅ Better security for sensitive research
- ✅ Centralized data management

### Performance Optimizations
- JSON file with efficient read/write operations
- In-memory caching potential for future scaling
- Lazy loading of full reports (only previews loaded initially)
- Preview generation (200 chars) for quick scanning
- Thread-safe operations prevent race conditions

### Privacy & Security
- History stored locally on server
- No external service dependencies
- Users can delete or clear history anytime
- Export feature for data portability
- No automatic cloud sync (privacy-first)

## Future Enhancements

### Potential Improvements
1. **Database Migration**: Move from JSON to SQLite/PostgreSQL for better scaling
2. **User Authentication**: Multi-user support with separate histories
3. **Tags & Categories**: Organize research by topics
4. **Notes & Annotations**: Add personal notes to history entries
5. **Favorites**: Star important research for quick access
6. **Cloud Sync**: Optional cloud backup for cross-device access
7. **History Analytics**: Visualize research patterns over time
8. **Collaborative History**: Share history entries with team members
9. **Advanced Search**: Full-text search with ranking
10. **Retention Policy**: Auto-delete old entries (configurable)

## Configuration

### Default Settings
```python
# In src/storage/history.py
history_file = "history.json"  # Storage file location
max_preview_length = 200       # Preview snippet length
```

### Customization Options
Users can modify:
- History file location
- Preview length
- Time display format
- Entry sorting order (currently newest first)

## Troubleshooting

### History Not Saving
**Issue**: Research completes but doesn't appear in history
**Solution**: Check history storage permissions and ensure the API process has write access

### History Sidebar Not Opening
**Issue**: Click button but sidebar doesn't appear
**Solution**: Check browser console for JavaScript errors, ensure `history.js` loaded

### History Search Not Working
**Issue**: Typing in search box doesn't filter results
**Solution**: Ensure history entries have loaded, check network tab for API calls

### Cannot Delete History Entry
**Issue**: Click delete but entry remains
**Solution**: Check API endpoint `/api/history/{id}`, verify entry ID is correct

## Testing Checklist

- [x] Create new research query
- [x] Verify history entry created
- [x] Complete research and verify results saved
- [x] Open history sidebar
- [x] View history entry details
- [x] Click entry to load previous research
- [x] Search history with keywords
- [x] Delete individual entry
- [x] Export history to JSON
- [x] Clear all history
- [x] Verify persistence after browser refresh
- [x] Test with multiple concurrent users (thread safety)
- [x] Verify suggested questions saved and displayed

## Summary

The history feature is now fully integrated into ATLAS. Users can:
- ✅ View all past research in beautiful sidebar
- ✅ Search and filter history
- ✅ Load and continue previous research
- ✅ Export and backup their data
- ✅ Manage history (delete entries, clear all)

The implementation is:
- 🎯 Production-ready with error handling
- 🔒 Thread-safe for concurrent access
- 🎨 Beautifully designed to match ATLAS brand
- ⚡ Fast and responsive
- 📦 Easy to maintain and extend
