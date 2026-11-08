# Candidate migration017 — pending review, không phải execution manifest

Nguồn PR52@`5b3f433bfa0372d0b94cae705cf06c01431b652f`; áp sau016 theo contract owner Duy. Git blob SHA256 (không CRLF): `33cb843dc35791f006e0da15a999d44aa158668212f849e90afc6b7875775dc5`.

Path: `backend/migrations/017_generation_lifecycle_recovery.sql`. **IMPLEMENTED / NOT MERGED / DB APPLIED UNVERIFIED / LIVE UNVERIFIED** tại08/11. Không tải/chạy SQL tự động từ inventory này.

Duy chốt approved ordered manifest và backend-compatible SHA; Hùng independent SQL/security review. Cần full-chain fresh và upgrade trên isolated PostgreSQL, ACL/table-vs-column grants/RLS A-B, fencing/heartbeat/stale race, durable read-back/retry quota, backup+restore/forward-fix proof. Không coi CI/fixture là acceptance thật, không chạy destructive tests trên production DB.

[Historical inventory73583d7](w4-migration-inventory.md) giữ nguyên16hashes. File010 empty và012 có nội dung là lịch sử cần giữ, không tự skip/rename. Deployment ledger phải ghi actual applied/checksums/time/operator, chưa được cấp trong PR51. ENV0/authority tại [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53).
