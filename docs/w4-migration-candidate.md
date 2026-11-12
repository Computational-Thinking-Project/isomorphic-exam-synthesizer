# Candidate migration017 — pending review, không phải execution manifest

Nguồn PR52@`9e9d6f366861d153c2e72deef3c2af93b0e1f0ff`; áp sau016 theo contract owner Duy. Git blob SHA256 (không CRLF): `d84880d30ff372b22ecdbc0e94efd11135869209c3695235467e7e1cf0d7ca4b`.

Path: `backend/migrations/017_generation_lifecycle_recovery.sql`. **IMPLEMENTED / NOT MERGED / DB APPLIED UNVERIFIED / LIVE UNVERIFIED** tại08/11. Không tải/chạy SQL tự động từ inventory này.

Duy chốt approved ordered manifest và backend-compatible SHA; Hùng independent SQL/security review. Cần full-chain fresh và upgrade trên isolated PostgreSQL, ACL/table-vs-column grants/RLS A-B, fencing/heartbeat/stale race, durable read-back/retry quota, backup+restore/forward-fix proof. Không coi CI/fixture là acceptance thật, không chạy destructive tests trên production DB.

[Historical inventory73583d7](w4-migration-inventory.md) giữ nguyên16hashes. File010 empty và012 có nội dung là lịch sử cần giữ, không tự skip/rename. Deployment ledger phải ghi actual applied/checksums/time/operator, chưa được cấp trong PR51. ENV0/authority tại [Issue53](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/issues/53).

Review Đạt tại9e9d6f3: embedded PostgreSQL fullchain/ACL/fencing/read-back/retry/replay probe đã chạy; không thay real PostgreSQL multi-connection races/PostgREST. [F01 test message guard009](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/pull/52#pullrequestreview-5817583465) còn mandatory; chưa approve/applied/live.
