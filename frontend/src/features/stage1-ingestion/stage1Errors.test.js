import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readIncompleteError } from './stage1Errors.js';

const cause = (errors, status = 422) => ({ response: { status, data: { detail: { errors } } } });

test('incomplete: nhãn toàn đề/câu và hướng sửa key, không đoán hoặc đổi thứ tự câu', () => {
  const model = readIncompleteError(cause([
    { question_no: 3, error_type: 'MISSING_ANSWER' },
    { question_no: 0, error_type: 'INVALID_FORMAT', message: 'No valid questions' },
    { question_no: 1, error_type: 'EMPTY_STEM' },
  ]));
  assert.match(model.message, /Chưa đọc được đầy đủ/);
  assert.deepEqual(model.errors.map(e => e.location), ['Câu 3', 'Toàn đề', 'Câu 1']);
  assert.match(model.errors[0].guidance, /đáp án đúng \(A\/B\/C\/D\)/);
  assert.match(model.errors[0].guidance, /đáp án tương ứng vào bảng đáp án cuối đề/);
  assert.match(model.errors[1].guidance, /1 đến 20/);
  assert.equal(model.errors[1].detail, 'No valid questions');
  assert.match(model.errors[2].guidance, /Bổ sung nội dung/);
});

test('công thức/hình: hướng sửa nguồn rõ ràng, không hứa OCR hoặc sửa câu đã parse', () => {
  const { errors } = readIncompleteError(cause([
    { question_no: 1, error_type: 'UNPARSED_OMML' },
    { question_no: 2, error_type: 'UNPARSED_IMAGE' },
  ]));
  assert.match(errors[0].guidance, /văn bản hoặc LaTeX/);
  assert.match(errors[1].guidance, /ngoài phạm vi/);
});

test('các lỗi cấu trúc/key/số câu có hướng sửa đầu vào phù hợp', () => {
  const expected = [
    ['AMBIGUOUS_FORMAT', /phương án A–D/],
    ['CONFLICTING_ANSWER_KEY', /một đáp án đúng/],
    ['SURPLUS_ANSWER_KEY', /đáp án thừa/],
    ['DUPLICATE_QUESTION_NO', /không trùng/],
    ['INVALID_QUESTION_NO', /số nguyên dương/],
  ];
  const { errors } = readIncompleteError(cause(expected.map(([error_type]) => ({ question_no: 2, error_type }))));
  expected.forEach(([, hint], index) => assert.match(errors[index].guidance, hint));
  assert.equal(errors.length, expected.length); // Multiple errors on one question are not deduplicated.
});

test('vị trí sai không hiển thị Câu0, Câuâm hoặc ép string thành số', () => {
  const numbers = [-1, 1.5, '3', null, undefined, NaN, Infinity];
  const { errors } = readIncompleteError(cause(numbers.map(question_no => ({ question_no, error_type: 'INVALID_QUESTION_NO' }))));
  assert(errors.every(e => e.location === 'Chưa xác định vị trí'));
});

test('mã mới và tên trùng prototype vẫn có fallback, message thiếu không làm crash', () => {
  for (const error_type of ['FUTURE_ERROR', '__proto__', 'constructor']) {
    const { errors } = readIncompleteError(cause([{ question_no: 5, error_type, message: null }]));
    assert.equal(errors[0].title, 'Lỗi nội dung chưa xác định');
    assert.equal(errors[0].detail, '');
    assert.match(errors[0].guidance, /nguồn rồi nạp lại/);
  }
});

test('trộn item malformed giữ vị trí và fallback từng item, không mất lỗi còn dùng được', () => {
  const { errors } = readIncompleteError(cause([
    null, { question_no: 2, message: 'Thông tin mới từ parser' }, [],
    { question_no: 4, error_type: 'MISSING_ANSWER', message: 123 },
  ]));
  assert.equal(errors.length, 4);
  assert.equal(errors[0].location, 'Chưa xác định vị trí');
  assert.equal(errors[1].detail, 'Thông tin mới từ parser');
  assert.equal(errors[2].title, errors[0].title);
  assert.equal(errors[3].detail, '');
  assert.match(errors[3].guidance, /đáp án đúng/);
});

test('envelope không có item hữu ích giữ fallback chung, không mở dialog rỗng', () => {
  for (const errors of [undefined, null, {}, 'invalid', [], [null, [], 'bad', 1, {}, { question_no: 1 }, { error_type: ' ', message: [] }]]) {
    assert.equal(readIncompleteError(cause(errors)), null);
  }
});

test('không nhầm FastAPI/confirm422 hoặc status khác thành incomplete ingestion', () => {
  for (const detail of [undefined, null, 'No questions', [{ loc: ['body'], msg: 'required' }]]) {
    assert.equal(readIncompleteError({ response: { status: 422, data: { detail } } }), null);
  }
  for (const status of [200, 400, 401, 403, 404, 408, 409, 429, 500, 503, '422', null]) {
    assert.equal(readIncompleteError(cause([{ error_type: 'MISSING_ANSWER' }], status)), null);
  }
  for (const error of [undefined, null, new Error('timeout'), { code: 'ERR_CANCELED' }, { response: { status: 422 } }]) {
    assert.equal(readIncompleteError(error), null);
  }
});

test('model mới, raw cause không bị sửa; giữ công thức/markup/text dài dưới dạng string', () => {
  const message = '<img src=x onerror=alert(1)> $x\\ne3$\n' + 'Nguồn '.repeat(1000);
  const item = Object.freeze({ question_no: 2, error_type: 'FUTURE_ERROR', message });
  const error = cause(Object.freeze([item]));
  Object.freeze(error.response.data.detail);
  const first = readIncompleteError(error);
  const second = readIncompleteError(error);
  assert.equal(first.errors[0].detail, message.trim());
  assert.notEqual(first, second);
  first.errors[0].detail = 'đã đổi view model';
  assert.equal(item.message, message);
  assert.equal(second.errors[0].detail, message.trim());
});
