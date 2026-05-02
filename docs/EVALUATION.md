# ATLAS Evaluation Framework

Tài liệu này hướng dẫn cách sử dụng và đóng góp vào hệ thống đánh giá (Evaluation) của ATLAS, đặc biệt là `golden dataset`, tích hợp RAGAS, và cấu hình `LLM Judge`.

## 1. Golden Dataset (Tập dữ liệu chuẩn)

ATLAS sử dụng một *Golden Dataset* (tập dữ liệu chuẩn) làm tiêu chuẩn để đánh giá chất lượng (offline evaluation) đối với các module Truy xuất (Retrieval) và Sinh ngữ cảnh (Generation). 
Do mục đích của ATLAS là phục vụ quy trình nghiên cứu (cho AI researchers và engineers), các mẫu trong Golden Dataset phải là các truy vấn mang tính học thuật (ví dụ: các kiến trúc AI, contrastive learning, LLMs...).

Dataset mẫu được đặt tại: `examples/evaluation/golden_dataset.jsonl`

### Định dạng của Golden Dataset
Mỗi dòng trong file `jsonl` là một đối tượng JSON đại diện cho một `EvaluationSample`. 

Các trường quan trọng:
- `id` (string): Định danh duy nhất của mẫu.
- `query` (string): Câu hỏi đầu vào của người dùng.
- `expected_behavior` (string): Hành vi mong đợi, thường là `"answer"` (trả lời) hoặc `"refuse"` (từ chối do vi phạm an toàn/ngoài phạm vi).
- `ground_truth_answer` (string): Câu trả lời đúng chuẩn.
- `ground_truth_context` (list[string]): Danh sách các đoạn văn bản (context) chuẩn xác để đối chiếu (giúp đánh giá Recall/Precision của mô hình truy xuất).
- `rubric` (object): Tiêu chí đánh giá phụ trợ (ví dụ: `domain` = "qa", "paper_recommendation", "deep_analysis").

### Hướng dẫn thêm dữ liệu vào Golden Dataset
- **Bởi con người:** Chuyên gia AI / Kỹ sư tạo thêm các câu hỏi phức tạp (chẳng hạn yêu cầu so sánh kiến trúc, giải thích paper mới) bằng cách thêm 1 dòng JSON tuân theo cấu trúc trên vào file `.jsonl`.
- **Bởi AI:** Bạn có thể viết một script dùng LLM để sinh ra các cặp `(query, ground_truth_answer, ground_truth_context)` từ kho tài liệu gốc, sau đó append vào file `golden_dataset.jsonl`.

### Chạy thử Evaluation với Golden Dataset
Bạn có thể chạy đánh giá offline với dataset bằng lệnh sau:
```bash
.\.venv\Scripts\python.exe -m src.quality.evaluation.evaluator examples/evaluation/golden_dataset.jsonl --markdown
```
*(Lưu ý: Chạy trực tiếp qua CLI trên dataset gốc sẽ không có prediction nên kết quả mặc định là FAIL do output trống. Trong thực tế, bạn cần truyền prediction output vào runtime).*

---

## 2. RAGAS Adapter (Best-effort)

ATLAS tích hợp thư viện [RAGAS](https://docs.ragas.io/) để bổ sung thêm các metrics đánh giá (như `faithfulness`, `response_relevancy`, `context_precision`, và `context_recall`).

Tuy nhiên, do API của RAGAS thay đổi thường xuyên, **RAGAS Adapter trong ATLAS hoạt động ở chế độ Best-effort**:
- Hệ thống cố gắng import và chạy RAGAS.
- Nếu môi trường không có `ragas`, hoặc gặp API không tương thích (gây lỗi runtime), ATLAS sẽ **bỏ qua lỗi một cách êm ái (graceful degradation)** và chỉ trả về các metrics nội bộ (ATLAS deterministic/LLM Judge metrics).

**Cách cài đặt (Tùy chọn):**
```bash
pip install ragas datasets
```

---

## 3. Cấu hình LLM Judge cho Online Evaluation

Mặc định, ATLAS chạy đánh giá (cả trong online và offline) bằng các phép đo **deterministic** (đếm từ khóa, string matching cơ bản) để tiết kiệm chi phí, **tránh làm chậm production** và ngăn các rủi ro downtime do LLM judge timeout.

Nếu bạn muốn đánh giá **"judge thật"** bằng LLM để đạt độ chính xác cao về mặt ngữ nghĩa (cho các tiêu chí như *Relevance*, *Faithfulness*...), bạn **phải cấu hình biến `EVAL_LLM_MODEL`**.

### Cách bật LLM Judge (qua môi trường hoặc `config.json`):

Ví dụ qua Environment Variables (Powershell):
```powershell
$env:ENABLE_EVALUATION="true"
$env:EVALUATION_MODE="online"
$env:EVAL_LLM_PROVIDER="openai"      # Hoặc "same_as_main"
$env:EVAL_LLM_MODEL="gpt-4o-mini"
```

Khi cấu hình này được kích hoạt, `EvaluationRunner` sẽ gọi LLM Judge để chấm điểm, cung cấp các metrics sâu sắc hơn nhiều so với hệ thống đo bằng regex mặc định.
