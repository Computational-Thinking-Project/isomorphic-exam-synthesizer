# Đối chiếu Ruff format trước sửa

ruff 0.17.1; config: backend/pyproject.toml
Working tree: 60; origin/dev: 49; baseline không còn lỗi ở working tree: 0.

Danh sách 65 tệp của lượt trước gồm 60 tệp bên dưới cộng 5 tệp đã được
Ruff định dạng ở lượt trước (theo lệnh `ruff format` và kết quả `5 files reformatted`):

- `backend/app/services/finalize/shuffle_input.py`
- `backend/tests/api/test_finalize_shuffle.py`
- `backend/tests/migrations/test_shuffle_writer_db.py`
- `backend/tests/services/finalize_test_client.py`
- `backend/tests/services/test_finalize_shuffle_input.py`

## TASK-305: cần sửa (11)

- `backend/app/main.py`
- `backend/app/models/schemas.py`
- `backend/app/services/finalize/repository.py`
- `backend/app/services/finalize/service.py`
- `backend/tests/api/test_finalize.py`
- `backend/tests/migrations/test_finalize_readiness.py`
- `backend/tests/services/isolated_postgres.py`
- `backend/tests/services/test_finalize_display_contract.py`
- `backend/tests/services/test_finalize_real_db_integration.py`
- `backend/tests/services/test_isolated_postgres_fixture.py`
- `backend/tests/services/test_review_real_db_integration.py`


## Đã lỗi trên origin/dev (49)

- `backend/app/api/dependencies.py`
- `backend/app/api/routes/sessions.py`
- `backend/app/api/routes/users.py`
- `backend/app/core/config.py`
- `backend/app/models/generation.py`
- `backend/app/models/targeted.py`
- `backend/app/services/ai/client.py`
- `backend/app/services/ai/gateway.py`
- `backend/app/services/ai/mock_client.py`
- `backend/app/services/ai/schema_repair.py`
- `backend/app/services/blueprint/adapters.py`
- `backend/app/services/blueprint/producer.py`
- `backend/app/services/blueprint/service.py`
- `backend/app/services/exporter/bundle_builder.py`
- `backend/app/services/exporter/source_renderer.py`
- `backend/app/services/exporter/typst_converter.py`
- `backend/app/services/generation/generator.py`
- `backend/app/services/generation/prompts.py`
- `backend/app/services/generation/service.py`
- `backend/app/services/generation/targeted_service.py`
- `backend/app/services/parser/blueprint_service.py`
- `backend/app/services/parser/docx_parser.py`
- `backend/app/services/parser/ingestion_service.py`
- `backend/app/services/parser/latex_parser.py`
- `backend/app/services/parser/markdown_parser.py`
- `backend/app/services/parser/utils.py`
- `backend/app/services/parser/validator.py`
- `backend/app/services/review/repository.py`
- `backend/app/services/review/service.py`
- `backend/tests/ai/test_blueprint_service.py`
- `backend/tests/ai/test_client.py`
- `backend/tests/ai/test_gateway.py`
- `backend/tests/ai/test_generation_pipeline.py`
- `backend/tests/ai/test_key_pool.py`
- `backend/tests/ai/test_schema_repair.py`
- `backend/tests/ai/test_targeted_regeneration.py`
- `backend/tests/api/conftest.py`
- `backend/tests/api/test_auth.py`
- `backend/tests/api/test_ingest.py`
- `backend/tests/api/test_legacy_blueprint_helpers.py`
- `backend/tests/api/test_ownership.py`
- `backend/tests/api/test_review_rpc_http.py`
- `backend/tests/api/test_sessions.py`
- `backend/tests/exporter/test_bundle_builder.py`
- `backend/tests/exporter/test_export_pipeline.py`
- `backend/tests/generation/test_generator.py`
- `backend/tests/services/__init__.py`
- `backend/tests/services/test_review_flow.py`
- `backend/tests/test_parsers.py`

## Ngoài phạm vi, mới so với origin/dev (0)
