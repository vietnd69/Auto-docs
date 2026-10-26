# Final review qua Claude Code / Codex subscription

Harness hỗ trợ `final_review_backend = "opencode" | "claude-code" | "codex"`.
Hai backend native gọi CLI chính thức trên máy, dùng phiên đăng nhập của người dùng.
Không trích xuất token subscription để đưa qua proxy hoặc OpenCode.

Phạm vi hiện tại: **final reviewer khi chạy `--resume-review`**. Generation, writer,
planner, reflector và đề xuất skill của Harness² vẫn dùng routing OpenCode/API hiện có.
Mặc định vẫn là `opencode`; không tự đổi model/nhà cung cấp khi đăng nhập hoặc quota lỗi.

## Đăng nhập và kiểm tra

```powershell
claude auth login
codex login
.venv/Scripts/python.exe scripts/subscription_status.py
```

Chỉ đăng nhập CLI sẽ dùng. Lệnh status không gọi model và chỉ in trạng thái đăng nhập,
không in email, token hoặc account ID. Không nhập API key nếu muốn dùng subscription.
Claude cần phiên đăng nhập có subscription; Codex cần đăng nhập ChatGPT.

Trong `[harness]` của `config.toml`:

```toml
final_review_backend = "codex" # hoặc "claude-code"
codex_subscription_model = "" # rỗng: dùng model mặc định được account/CLI hỗ trợ
claude_subscription_model = "" # có thể dùng alias sonnet nếu account hỗ trợ
codex_subscription_effort = "medium"
claude_subscription_effort = "high"
codex_bin = "" # rỗng: tìm trên PATH; có thể chỉ định đường dẫn executable
claude_bin = ""
final_review_seconds = 120
```

Hoặc chọn cho terminal hiện tại:

```powershell
$env:MOD_DOC_HARNESS_FINAL_REVIEW_BACKEND = "codex"
```

Sau khi đã có checkpoint của page, chạy `mod-harness run-page PAGE_ID --resume-review`
với **đúng** `--state-dir` và `--harness-tree` của checkpoint. Các tham số `--result`
và `--events` vẫn dùng được. Không thêm `--publish` cho trial đánh giá chất lượng.
Thay backend không bỏ qua xác minh source, draft, ledger hoặc skill của checkpoint.

## Review và usage

Đặt `review_runtime_evidence = 1` trong `[harness]` để controller chạy các probe
LuaJIT cố định trước khi gọi final reviewer (cả native và OpenCode resume-review).
`runtime_lua_bin` để rỗng sẽ tìm `luajit` trên PATH. Probe lỗi, timeout hoặc output
không đầy đủ sẽ dừng trước model; không thay bằng kiến thức tự đoán.
Artifact `reports/runtime-evidence/JOB.json` lưu phiên bản, executable/probe hash,
source revision, mã probe và stdout. Ngữ cảnh review nhận kết quả đã xác minh,
gồm numeric-string coercion theo phép toán, false/nil fallback, table keys và
chia cho zero. Đây là standalone LuaJIT, không chứng minh runtime trong game DST,
không chạy mã model sinh ra và không tự tạo verdict PASS.

`scripts/runtime_holdout_trial.py --area outputs/<thu-muc-moi>` kiểm tra regression
counter rồi so baseline/candidate trên finiteuses với cùng input và runtime
evidence. Candidate đóng băng từ counter; không tune lại trên finiteuses. Draft cũ
được giữ nguyên bản provenance, metadata target được chuẩn hóa riêng trước review.
Sau A/B, trial cho một vòng repair và review độc lập, không publish/promote.

- Controller vẫn nạp skill đã đóng băng và ghi hash.
- MCP native chỉ công bố các tool review; không có tool sửa docs hoặc plan.
- Claude dùng cấu hình MCP riêng, không có built-in shell/editor. Codex dùng
  sandbox read-only, tắt shell, cấu hình MCP và allowlist tool cho riêng lượt này.
- API key, proxy endpoint và các biến chọn nhà cung cấp trả phí không được truyền
  sang CLI. Lỗi login/quota trả lỗi; không có fallback sang API key.
- Vẫn cần đọc đủ source/draft, ledger sạch và receipt hợp lệ. Exit code 0 hoặc
  câu trả lời "PASS" của model không tự tạo receipt.
- Giới hạn wall-clock vẫn áp dụng. `final_review_steps` là giới hạn OpenCode;
  không được trình bày như một giới hạn token/turn của native CLI.
- Log chuẩn: `reports/sessions/JOB.jsonl`; log native: `JOB.native.jsonl`;
  stderr: `JOB.stderr.txt`; usage: `JOB.usage.json`.
- `billing_mode = subscription`, `cost_usd = null`. Token usage và chi phí CLI
  báo (nếu có) được lưu riêng. Chi phí CLI báo không nhất thiết là tiền trừ thực
  tế từ subscription. Hạn mức, extra usage/credits phụ thuộc cài đặt tài khoản.
  Không coi subscription là miễn phí hoặc giả định có thể bảo đảm trần USD bằng
  cách đếm token như API.
- Script `harness2_budget_trial.py` ép backend về OpenCode để mọi request của
  trial có trần USD vẫn đi qua chung SpendGate; không âm thầm gọi native bên ngoài gate.

## Kiểm chứng

### Trial một trang: sửa docs và đề xuất skill

`scripts/subscription_full_flow.py --area outputs/<thu-muc-moi>` chạy thử trên
checkpoint counter đã có: nhập findings đã xác minh → Sol medium sửa → Sonnet
5.5 high review độc lập → Harness2 Proposer đề xuất quy tắc → adapter kiểm tra
candidate → Sol đánh giá bản sửa và replay mù trên bản lỗi gốc.

Writer chỉ có quyền sửa trang được controller chỉ định và không được đóng ledger.
Reviewer không có tool sửa docs. Proposer chỉ trả JSON, controller chỉ nối quy tắc
vào candidate `review-symbols` sau kiểm tra giới hạn và chống lộ đáp án của task.
Tối đa 2 vòng repair/review, 1 proposal và 2 replay; mỗi native session tối đa 300s.
`--phase repair|review|propose|evaluate` với cùng `--area` cho phép tiếp tục từng bước;
log đã tồn tại không tự chạy lại request bị gián đoạn.

Đây là thử nghiệm một trang dùng Harness2 Proposer và adapter guards, **không phải**
toàn bộ lịch `run_sequential`, chưa chứng minh khả năng tổng quát hóa hay tiết kiệm.
Không publish docs hoặc promote skill production. Cần regression trên ít nhất hai
trang khác nhau và accounting phù hợp trước promotion; chi phí subscription thực
tế vẫn là `null`, không dùng estimate của CLI để giả lập chi phí thực.

Đã kiểm tra CLI help, trạng thái login và test offline: routing, bỏ API key,
auth chưa đủ, allowlist MCP, timeout, terminal result/error và usage không giả `$0`.
Đã chạy model thật trên bản counter ngày 2026-10-27: GPT-6.1-Sol medium và
`claude-sonnet-5-5` high đều hoàn tất, đọc đủ source/draft và giữ mở findings đúng.
Sol có 6 findings, Sonnet 5.5 có 1 finding bổ sung; tất cả được kiểm chứng bằng LuaJIT.
Chi tiết: `outputs/harness2-trial-20261027-015006-subscriptions/COMPARISON.md`.
Alias `sonnet` trên CLI được thử đã trỏ tới 4.6, nên phải chỉ định model ID chính xác
nếu cần 5.5. Codex cần cấu hình approval riêng cho các tool MCP review; adapter chỉ
cấp quyền cho allowlist đó, không mở toàn bộ tools hoặc bỏ sandbox.

Tài liệu chính thức:

- [Claude Code chạy bằng chương trình](https://code.claude.com/docs/en/headless)
- [Codex authentication](https://developers.openai.com/codex/auth/)
- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
