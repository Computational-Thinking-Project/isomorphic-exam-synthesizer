# Canonical source artifact status (TASK-204 Q02)

Mapping profile **1.0**, pinned consumer evidence:
[BE2 contract at 7e9377f](https://github.com/Computational-Thinking-Project/isomorphic-exam-synthesizer/blob/7e9377fd75fbb19b732d4dc154254e8a8669d22d/docs/api/generation-config-endpoint.md),
backed by `015_stage2_canonical_w2_integration.sql` on that same commit.
This branch does not merge/deploy those generation RPCs. FE2 acceptance and
cross-PR integration remain pending; these are not locally merged consumers.

| Canonical dimension | Accepted public IDs (exact case) | FE label |
|---|---|---|
| values | NUMERICAL, parameter_variation | Thay đổi số liệu / tham số |
| context | context_swap | Đổi ngữ cảnh thực tế |
| wording, names, representation, option_order | none in public profile 1.0 | not exposed |

The callable AI service accepts canonical dimensions, while public configuration
accepts only the aliases above. Unknown/missing dimensions or malformed policy
fail closed. Known dimensions without a public alias are valid and yield no mode.
SHUFFLE and variable_inversion are not public modes. Ordering is separate.

GET `/api/sessions/{id}/source-artifacts` keeps all existing fields and adds
`supported_modes` from the **same RPC and lock** as readiness. Each mode is
`{id, label, description, question_count, is_available}`. Count distinct source
questions, including a mode once per question regardless of repeated transforms.
`is_available` is true exactly when count equals total_questions. Partial modes
remain in the list disabled. Sort by exact public ID. Labels reuse existing FE
metadata; FE2 still needs to adopt the canonical endpoint and confirm display.

| canonical_status | ready | supported_modes |
|---|---|---|
| pending | false | null |
| running | false | null |
| failed | false | null |
| ready | true | array of mode objects |
| ready, no mapped dimension (Original Clone / NONE-only) | true | [] |

Example mode array for a one-question values/context Blueprint:

```json
[
  {"id":"NUMERICAL","label":"Thay đổi số liệu / tham số","description":"Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.","question_count":1,"is_available":true},
  {"id":"context_swap","label":"Đổi ngữ cảnh thực tế","description":"Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.","question_count":1,"is_available":true},
  {"id":"parameter_variation","label":"Thay đổi số liệu / tham số","description":"Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.","question_count":1,"is_available":true}
]
```

The production list always includes each confirmed question. Ready with [] is
valid; consumers must test `ready === true`. Never infer readiness from legacy
question_blueprints, absent fields or truthiness of modes. An empty transformations
array is invalid canonical v0.4.0 (schema minItems=1); test Original Clone using a
valid Blueprint whose transformations have only unmapped known dimensions.
