# W4 migration inventory — static Git bytes

Đạt lập 07/11/2026 từ dev `73583d775243245cd2479e29d943c329b0b2debb`. Đây là inventory, **không phải approved migration order hay DB-applied ledger**. SHA256 tính trên blob Git, không dùng working-copy CRLF. [Acceptance và owner](w4-ops-handoff.md#4-migration-inventory-và-acceptance-gate).

| Path | SHA256 của Git blob | DB applied / fresh+upgrade proof |
|---|---|---|
| `backend/scripts/schema.sql` | `0710b6a7638101ec9571699e2d0208761461ee7eaf3e72858c173387fe468e35` | UNVERIFIED |
| `backend/migrations/002_replace_source_questions_rpc.sql` | `8dae5f4d5b5cd05d098faa5cfa8b13ff34e40d31b60de2f545b6407eabf6d0d0` | UNVERIFIED |
| `backend/migrations/003_confirm_exam_source_rpc.sql` | `9d410a002820d8b5b49bca02f0e9882fa3182f553a295a57a8d1f003dbb34093` | UNVERIFIED |
| `backend/migrations/004_save_generation_config_rpc.sql` | `c66a1416b875ee407f0663301d841120cf9b5b5c16480ea07aea4435583aba25` | UNVERIFIED |
| `backend/migrations/005_generation_job_operations_rpc.sql` | `55d3d51d1608ad4ec6c57d542428af728d6cdec28373846d0752018da4f1ea65` | UNVERIFIED |
| `backend/migrations/006_stage3_review_and_shuffle.sql` | `c6a50d885f0382c791db2ad7dcd1450c4f766e58d2884dbae615a8028daa27c5` | UNVERIFIED |
| `backend/migrations/007_finalize_approve_session_rpc.sql` | `bd2ccc61b9ce14e1661c50c5671fc2e4da2baf4a681b52a4c5d13cf60acca78e` | UNVERIFIED |
| `backend/migrations/008_finalize_persist_shuffle_rpc.sql` | `f32935cbf48a27d2c8c988ba8dfc1accefdb48300b9e273c094710b63d18d63f` | UNVERIFIED |
| `backend/migrations/009_finalize_security_boundary.sql` | `b4516597de80f8678381968678b46748ff92a4d7c7b4ad581fc3378cb6ac4bef` | UNVERIFIED |
| `backend/migrations/010_source_artifact_supported_modes.sql` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | UNVERIFIED |
| `backend/migrations/011_source_confirmation_revision.sql` | `e450637bac39ff47c3677de497d84bc42aba948dac656f6c4009f67135a8f0cf` | UNVERIFIED |
| `backend/migrations/012_source_artifact_supported_modes.sql` | `dd58de9603cf36fefd794dcbd5904c52c9216d10014fdd13edc63691218ef54d` | UNVERIFIED |
| `backend/migrations/013_source_freeze_guard.sql` | `1a04b5ff975a68605cd8eed9b1fc579a33f1b3f5897b738863a41989413e39ff` | UNVERIFIED |
| `backend/migrations/014_disable_legacy_source_confirmation.sql` | `9f408a274739b82ae94803aff1bee594ab4a0111273bdfb08410366ea59a4113` | UNVERIFIED |
| `backend/migrations/015_stage2_canonical_w2_integration.sql` | `63b18dc6b541ec48c55ee3e4d5371cb8f84bc96c429b85f052feeb260521dc1b` | UNVERIFIED |
| `backend/migrations/016_stage2_original_clone.sql` | `539f929112eb1803fb0f4d1e5464155a07808e6640ecd6ce2bf42dca1a823427` | UNVERIFIED |

Duy/Hùng cần đối chiếu bootstrap và ledger thật, signatures/grants của RPC, version hiện có, các migration có tên gần nhau010/012 và chốt một manifest ordered. Không chạy file trong bảng chỉ vì đã có hash. Khi code/migration thay đổi, tạo inventory theo candidate SHA mới và kiểm lại; không sửa hash để khớp DB không rõ lịch sử.
